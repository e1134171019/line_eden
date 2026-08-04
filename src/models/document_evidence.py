# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

EXTRACTION_NATIVE_TEXT = "native_text"
EXTRACTION_HTML_TEXT = "html_text"
EXTRACTION_MULTIMODAL = "multimodal"


@dataclass(frozen=True)
class DocumentPageEvidence:
    """單一文件頁面的文字、擷取方法與穩定內容雜湊。"""

    page_number: int
    text: str
    extraction_method: str = EXTRACTION_NATIVE_TEXT

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("文件頁碼必須從 1 開始")

    @property
    def text_hash(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParsedDocument:
    """保留文件格式與逐頁文字證據。"""

    document_kind: str
    pages: tuple[DocumentPageEvidence, ...]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages if page.text.strip())

    @property
    def page_count(self) -> int:
        return len(self.pages)
