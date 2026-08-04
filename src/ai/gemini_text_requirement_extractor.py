# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

from google.genai import types

from src.ai.eligibility_evidence_compactor import compact_notice_content
from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    GeminiRequirementExtractor,
)
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    NoticeContent,
)


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
        compacted = compact_notice_content(fetch_result.content)
        prompt = _build_text_prompt(title, compacted)
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
        f"公告正文或資格相關節錄：\n{content.main_text}",
    ]
    parts.extend(
        _attachment_prompt(index, attachment)
        for index, attachment in enumerate(content.attachments, start=1)
        if attachment.text.strip()
    )
    parts.append(
        """
規則：
1. 只抽取文件明確寫出的申請資格，不得推測或評估學生是否符合。
2. 正文與附件若互相衝突，保留較具體且有資格語境的條件。
3. program_types 只能放日間部、進修部、在職專班等學制。
4. 科系、學系、學院與專業領域必須放 departments 欄位。
5. 輸入可能是長文件的資格相關節錄；若節錄不足以涵蓋全部必要資格，criteria_complete=false。
6. 附件若標出「第N頁」，evidence.page 必須填實際 N；沒有頁碼資訊時才填 1。
7. evidence.text 只能保留該頁中的短句，不得把不同頁面的文字合併成同一證據。
8. 申請表、聲明書、行政契約或其他支援文件不得假裝成 scholarship_rules。
""".strip()
    )
    return "\n\n".join(parts)


# 將逐頁附件證據放進提示；無頁碼的舊資料仍維持相容格式。
def _attachment_prompt(index: int, attachment: ExtractedAttachment) -> str:
    header = "\n".join(
        (
            f"主要辦法附件{index}：",
            f"標籤：{attachment.label}",
            f"角色提示：{attachment.role_hint}",
            f"內容角色：{attachment.content_role}",
            f"解析狀態：{attachment.status}",
            f"驗證狀態：{attachment.verification_status}",
            f"文件雜湊：{attachment.document_hash}",
            f"網址：{attachment.final_url or attachment.requested_url}",
        )
    )
    if not attachment.pages:
        return f"{header}\n資格相關節錄：\n{attachment.text}"
    pages = "\n".join(
        f"[第{page.page_number}頁｜{page.extraction_method}]\n{page.text}"
        for page in attachment.pages
        if page.text.strip()
    )
    return f"{header}\n逐頁資格相關節錄：\n{pages}"
