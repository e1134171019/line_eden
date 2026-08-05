# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from src.ai.eligibility_evidence_compactor import compact_notice_content
from src.diagnostics.detail_fetch_diagnostics import ExtractedAttachment, NoticeContent
import src.extractors.document_text_extractor as extractor
from src.models.document_evidence import DocumentPageEvidence


# PDF 空白頁不得造成後續資格頁碼重排。
def test_extract_document_preserves_original_pdf_page_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        SimpleNamespace(extract_text=lambda: ""),
        SimpleNamespace(extract_text=lambda: "申請資格：學業平均八十分以上。"),
        SimpleNamespace(extract_text=lambda: "排除進修部學生。"),
    ]
    monkeypatch.setattr(extractor, "PdfReader", lambda _: SimpleNamespace(pages=pages))

    parsed = extractor.extract_document(
        b"fake-pdf",
        extractor.PDF_MIME,
        "https://example.com/rules.pdf",
        max_pdf_pages=3,
    )

    assert [page.page_number for page in parsed.pages] == [2, 3]
    assert parsed.pages[0].text_hash
    assert "學業平均八十分以上" in parsed.text


# 舊版純文字介面仍應回傳逐頁合併文字。
def test_legacy_document_text_api_remains_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        SimpleNamespace(extract_text=lambda: "第一頁"),
        SimpleNamespace(extract_text=lambda: "第二頁"),
    ]
    monkeypatch.setattr(extractor, "PdfReader", lambda _: SimpleNamespace(pages=pages))

    text = extractor.extract_document_text(
        b"fake-pdf",
        extractor.PDF_MIME,
        "https://example.com/rules.pdf",
        max_pdf_pages=2,
    )

    assert text == "第一頁\n第二頁"


# 資格壓縮後仍須保留原始頁碼，供模型回傳可追溯證據。
def test_compactor_preserves_page_evidence() -> None:
    pages = (
        DocumentPageEvidence(2, "申請資格：電子工程系學生。" * 100),
        DocumentPageEvidence(4, "學業平均八十分以上。" * 100),
    )
    attachment = ExtractedAttachment(
        requested_url="https://example.com/rules.pdf",
        final_url="https://example.com/rules.pdf",
        label="申請辦法.pdf",
        role_hint="rules",
        content_role="scholarship_rules",
        document_kind="pdf",
        status="success",
        text="\n".join(page.text for page in pages),
        document_hash="abc",
        pages=pages,
        verification_status="parsed_with_page_evidence",
    )

    compacted = compact_notice_content(
        NoticeContent("公告正文", (attachment,), "resolved"),
        max_chars=500,
    )

    assert [page.page_number for page in compacted.attachments[0].pages] == [2, 4]
    assert len(compacted.attachments[0].text) <= 500
