# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

from google.genai import types

from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    GeminiRequirementExtractor,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, NoticeContent


@dataclass(frozen=True)
class PreparedGeminiText:
    """送往 Gemini 的正文與附件文字證據包。"""

    content_hash: str
    prompt: str


class GeminiTextRequirementExtractor:
    """將公告正文與已解析附件轉成結構化資格欄位。"""

    def __init__(self, extractor: GeminiRequirementExtractor) -> None:
        self.extractor = extractor

    def prepare(self, title: str, fetch_result: DetailFetchResult) -> PreparedGeminiText:
        prompt = _build_text_prompt(title, fetch_result.content)
        digest = sha256(prompt.encode("utf-8")).hexdigest()
        return PreparedGeminiText(digest, prompt)

    def count_tokens(self, prepared: PreparedGeminiText) -> int:
        # Google SDK 的 contents 聯集型別內含 Unknown；呼叫參數由本模組固定為 list[str]。
        response = self.extractor.client.models.count_tokens(  # pyright: ignore[reportUnknownMemberType]
            model=self.extractor.model,
            contents=[prepared.prompt],
        )
        tokens = int(response.total_tokens or 0)
        if tokens > self.extractor.max_input_tokens:
            raise ValueError(
                f"Gemini 單份文字輸入超過 {self.extractor.max_input_tokens} tokens"
            )
        return tokens

    def extract(self, prepared: PreparedGeminiText) -> GeminiApiResult:
        # Google SDK 的 contents 聯集型別內含 Unknown；回應再由 Pydantic Schema 驗證。
        response = self.extractor.client.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
            model=self.extractor.model,
            contents=[prepared.prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiRequirementExtraction,
                max_output_tokens=self.extractor.max_output_tokens,
            ),
        )
        extraction = GeminiRequirementExtraction.model_validate_json(response.text or "{}")
        usage = response.usage_metadata
        return GeminiApiResult(
            extraction,
            int(getattr(usage, "prompt_token_count", 0) or 0),
            int(getattr(usage, "candidates_token_count", 0) or 0),
            int(getattr(usage, "total_token_count", 0) or 0),
        )


def _build_text_prompt(title: str, content: NoticeContent) -> str:
    parts = [
        "你是獎學金申請資格文件抽取器。",
        f"公告標題：{title}",
        f"主要辦法狀態：{content.rules_status}",
        f"公告正文：\n{content.main_text}",
    ]
    for index, attachment in enumerate(content.attachments, start=1):
        if not attachment.text.strip():
            continue
        parts.append(
            "\n".join(
                (
                    f"附件{index}：",
                    f"標籤：{attachment.label}",
                    f"角色提示：{attachment.role_hint}",
                    f"內容角色：{attachment.content_role}",
                    f"解析狀態：{attachment.status}",
                    f"網址：{attachment.final_url or attachment.requested_url}",
                    f"內容：\n{attachment.text}",
                )
            )
        )
    parts.append(
        """
規則：
1. 只抽取文件明確寫出的申請資格，不得推測或評估學生是否符合。
2. 正文與附件若互相衝突，保留較具體且有資格語境的條件。
3. program_types 只能放日間部、進修部、在職專班等學制。
4. 科系、學系、學院與專業領域必須放 departments 欄位。
5. 若資訊不足以涵蓋全部必要資格，criteria_complete=false。
6. 文字輸入沒有可靠 PDF 頁碼；evidence.page 一律填 1，並在 evidence.text 保留短句來源。
7. 申請表、聲明書或證明文件不得假裝成 scholarship_rules。
""".strip()
    )
    return "\n\n".join(parts)
