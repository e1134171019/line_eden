# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Literal

from google import genai
from google.genai import types
import httpx
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter


class RequirementEvidence(BaseModel):
    """Gemini 回傳的單項資格證據。"""

    page: int = Field(ge=1, description="證據所在的 PDF 頁碼，第一頁為 1。")
    text: str = Field(description="文件中的短句證據，不得自行補充。")


class GeminiRequirementExtraction(BaseModel):
    """只描述公告文件條件，不包含使用者個人背景。"""

    document_type: Literal["scholarship_rules", "application_form", "other", "uncertain"]
    criteria_complete: bool
    needs_more_pages: bool
    applicant_groups: list[str] = Field(default_factory=list)
    degree_levels: list[str] = Field(default_factory=list)
    program_types_included: list[str] = Field(default_factory=list)
    program_types_excluded: list[str] = Field(default_factory=list)
    departments_included: list[str] = Field(default_factory=list)
    departments_excluded: list[str] = Field(default_factory=list)
    year_requirements: list[str] = Field(default_factory=list)
    required_special_statuses: list[str] = Field(default_factory=list)
    minimum_average_grade: float | None = None
    minimum_conduct_grade: float | None = None
    rank_requirement: str | None = None
    residence_requirement: str | None = None
    explicit_exclusions: list[str] = Field(default_factory=list)
    other_required_conditions: list[str] = Field(default_factory=list)
    evidence: list[RequirementEvidence] = Field(default_factory=list)

    # 將結構化欄位轉成既有規則可判斷的中文資格句型。
    def to_rule_text(self) -> str:
        lines = _joined_rules("申請對象為", self.applicant_groups)
        lines.extend(_joined_rules("申請對象限於", self.degree_levels))
        lines.extend(_joined_rules("申請對象為", self.program_types_included, "學生"))
        lines.extend(_list_rules("不包括", self.program_types_excluded))
        lines.extend(_joined_rules("申請資格限於", self.departments_included, "相關科系"))
        lines.extend(_list_rules("不包括相關科系：", self.departments_excluded))
        lines.extend(self.year_requirements)
        lines.extend(_joined_rules("申請資格限於", self.required_special_statuses))
        lines.extend(_score_rules(self.minimum_average_grade, self.minimum_conduct_grade))
        lines.extend(_optional_rules(self.rank_requirement, self.residence_requirement))
        lines.extend(_list_rules("不包括", self.explicit_exclusions))
        lines.extend(self.other_required_conditions)
        return "。".join(item.strip("。 ") for item in lines if item.strip()) + "。"


@dataclass(frozen=True)
class PreparedGeminiDocument:
    """已下載、雜湊並裁切頁數的 PDF。"""

    requested_url: str
    final_url: str
    document_hash: str
    pdf_bytes: bytes
    selected_pages: int


@dataclass(frozen=True)
class GeminiApiResult:
    """Gemini 結構化結果與實際 Token 使用量。"""

    extraction: GeminiRequirementExtraction
    input_tokens: int
    output_tokens: int
    total_tokens: int


class GeminiRequirementExtractor:
    """下載掃描 PDF，只傳少量頁面給 Gemini 抽取資格條件。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_pages: int,
        max_download_bytes: int,
        max_input_tokens: int,
        max_output_tokens: int,
        timeout_seconds: float,
        user_agent: str,
    ) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_pages = max_pages
        self.max_download_bytes = max_download_bytes
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    # 下載 PDF 並僅保留前 N 頁，完整文件雜湊仍用於永久快取。
    def prepare_document(self, url: str) -> PreparedGeminiDocument:
        final_url, content = self._download_pdf(url)
        selected, page_count = self._select_pages(content)
        return PreparedGeminiDocument(
            url,
            final_url,
            sha256(content).hexdigest(),
            selected,
            page_count,
        )

    # 在生成前先取得 Gemini 對文字與 PDF 的輸入 Token 計數。
    def count_tokens(self, title: str, document: PreparedGeminiDocument) -> int:
        contents = self._contents(title, document)
        response = self.client.models.count_tokens(model=self.model, contents=contents)
        tokens = int(response.total_tokens or 0)
        if tokens > self.max_input_tokens:
            raise ValueError(f"Gemini 單份文件輸入超過 {self.max_input_tokens} tokens")
        return tokens

    # 以 JSON Schema 要求 Gemini 只回傳資格欄位。
    def extract(self, title: str, document: PreparedGeminiDocument) -> GeminiApiResult:
        response = self.client.models.generate_content(
            model=self.model,
            contents=self._contents(title, document),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiRequirementExtraction,
                max_output_tokens=self.max_output_tokens,
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

    # 建立不含 profile.json 的文件抽取提示與 PDF 輸入。
    def _contents(self, title: str, document: PreparedGeminiDocument) -> list[object]:
        prompt = _build_prompt(title, document.selected_pages)
        pdf = types.Part.from_bytes(data=document.pdf_bytes, mime_type="application/pdf")
        return [prompt, pdf]

    # 以大小限制下載公開 PDF，避免外部資源無限制進入記憶體。
    def _download_pdf(self, url: str) -> tuple[str, bytes]:
        headers = {"User-Agent": self.user_agent}
        with httpx.Client(headers=headers, timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
        content = response.content
        if len(content) > self.max_download_bytes:
            raise ValueError("Gemini 文件超過下載安全上限")
        if not content.lstrip().startswith(b"%PDF"):
            raise ValueError("Gemini 備援目前只接受 PDF")
        return str(response.url), content

    # 使用 pypdf 重組前 N 頁，不把整份附件送往 Gemini。
    def _select_pages(self, content: bytes) -> tuple[bytes, int]:
        reader = PdfReader(BytesIO(content), strict=False)
        page_count = min(len(reader.pages), self.max_pages)
        if page_count < 1:
            raise ValueError("PDF 沒有可送出的頁面")
        writer = PdfWriter()
        for index in range(page_count):
            writer.add_page(reader.pages[index])
        output = BytesIO()
        writer.write(output)
        return output.getvalue(), page_count


# 建立限制模型只能依據所提供頁面的結構化抽取提示。
def _build_prompt(title: str, selected_pages: int) -> str:
    return f"""
你是獎學金申請資格文件抽取器。公告標題：{title}
目前只提供 PDF 前 {selected_pages} 頁。

規則：
1. 只抽取文件明確寫出的申請資格，不得推測、補齊或評估任何學生是否符合。
2. 保留文件中的中文身分、學制、科系、年級、成績、排名與戶籍用語。
3. 若所提供頁面不足以涵蓋主要申請資格，criteria_complete=false 且 needs_more_pages=true。
4. evidence 只放支持資格欄位的短句與實際頁碼，不要抄寫整份文件。
5. 申請表、封面或無關文件須正確標示 document_type，不得假裝是完整辦法。
""".strip()


# 將同一欄位的多個可申請對象放在同一句，避免誤判成互斥限制。
def _joined_rules(prefix: str, values: list[str], suffix: str = "") -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    if not cleaned:
        return []
    return [f"{prefix}{'及'.join(cleaned)}{suffix}"]


# 將必須逐項保留的排除條件轉成簡短資格句。
def _list_rules(prefix: str, values: list[str]) -> list[str]:
    return [f"{prefix}{value}" for value in values if value.strip()]


# 將最低學業與操行分數轉成既有規則可解析句型。
def _score_rules(average: float | None, conduct: float | None) -> list[str]:
    rules: list[str] = []
    if average is not None:
        rules.append(f"學業平均{average:g}分以上")
    if conduct is not None:
        rules.append(f"操行成績{conduct:g}分以上")
    return rules


# 加入排名與戶籍等非空白限制文字。
def _optional_rules(rank: str | None, residence: str | None) -> list[str]:
    return [item for item in (rank, residence) if item and item.strip()]
