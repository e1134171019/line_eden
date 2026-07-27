# -*- coding: utf-8 -*-

from io import BytesIO
from urllib.parse import urlparse

from docx import Document
from pypdf import PdfReader

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# 依內容類型或網址副檔名判斷可解析文件格式。
def detect_document_kind(content_type: str, source_url: str) -> str:
    normalized_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    suffix = urlparse(source_url).path.lower()
    if normalized_type == PDF_MIME or suffix.endswith(".pdf"):
        return "pdf"
    if normalized_type == DOCX_MIME or suffix.endswith(".docx"):
        return "docx"
    return "unsupported"


# 將支援的 PDF 或 DOCX 位元內容轉成純文字。
def extract_document_text(
    content: bytes,
    content_type: str,
    source_url: str,
    max_pdf_pages: int,
) -> str:
    kind = detect_document_kind(content_type, source_url)
    if kind == "pdf":
        return _extract_pdf_text(content, max_pdf_pages)
    if kind == "docx":
        return _extract_docx_text(content)
    raise ValueError("不支援的附件格式")


# 擷取 PDF 前指定頁數的文字，掃描型 PDF 無文字時拒絕誤判。
def _extract_pdf_text(content: bytes, max_pages: int) -> str:
    reader = PdfReader(BytesIO(content))
    page_texts = [page.extract_text() or "" for page in reader.pages[:max_pages]]
    text = _normalize_text("\n".join(page_texts))
    if not text:
        raise ValueError("PDF 沒有可擷取文字，可能是掃描檔")
    return text


# 擷取 DOCX 的段落與表格儲存格文字。
def _extract_docx_text(content: bytes) -> str:
    document = Document(BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    table_text = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    text = _normalize_text("\n".join([*paragraphs, *table_text]))
    if not text:
        raise ValueError("DOCX 沒有可擷取文字")
    return text


# 壓縮文件文字中的空白與空行。
def _normalize_text(text: str) -> str:
    return " ".join(text.split())
