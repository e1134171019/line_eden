# -*- coding: utf-8 -*-

from io import BytesIO
from zipfile import ZipFile

import pytest

from src.collectors.evidence_detail_fetcher import EvidenceDetailFetcher
from src.extractors.attachment_link_extractor import extract_attachment_inventory
from src.extractors.document_text_extractor import (
    detect_document_kind,
    extract_document_text,
)
from src.models.scholarship import Scholarship


def test_attachment_inventory_reads_data_url_and_onclick() -> None:
    html = """
    <main>
      <h1>能源獎學金申請公告</h1>
      <p>詳細辦法及申請資格請見附件。</p>
      <button data-url="/files/rules.odt">申請辦法</button>
      <a onclick="window.open('/files/form.docx')">申請表</a>
    </main>
    """

    inventory = extract_attachment_inventory(
        html,
        "https://example.test/news/1",
        "能源獎學金申請公告",
        5,
    )

    assert inventory.discovered_count == 2
    assert inventory.selected_urls[0] == "https://example.test/files/rules.odt"
    assert "https://example.test/files/form.docx" in inventory.selected_urls
    assert inventory.discovered_rules_count == 1


def test_odt_document_text_is_extracted() -> None:
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr(
            "content.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <office:document-content
              xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
              xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
              <office:body><office:text>
                <text:p>申請資格：國內大專校院學生。</text:p>
                <text:p>截止日期：2026年9月30日。</text:p>
              </office:text></office:body>
            </office:document-content>""",
        )

    text = extract_document_text(
        content.getvalue(),
        "application/vnd.oasis.opendocument.text",
        "https://example.test/rules.odt",
        5,
    )

    assert "申請資格" in text
    assert "2026年9月30日" in text


def test_legacy_doc_is_explicitly_diagnosed() -> None:
    assert detect_document_kind("application/msword", "rules.doc") == "doc_legacy"
    with pytest.raises(ValueError, match="舊式 DOC"):
        extract_document_text(
            b"legacy-binary",
            "application/msword",
            "https://example.test/rules.doc",
            5,
        )


def test_evidence_fetcher_passes_detail_url_to_base_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def fake_fetch(self: object, scholarship: Scholarship) -> object:
        captured.append(scholarship.source_url)
        from src.diagnostics.detail_fetch_diagnostics import (
            DetailFetchResult,
            ResourceDiagnostic,
        )

        source = ResourceDiagnostic(
            "source",
            scholarship.source_url,
            scholarship.source_url,
            "text/plain",
            10,
            "html",
            "success",
            10,
        )
        return DetailFetchResult("申請資格", source, tuple(), 0, body_text="申請資格")

    monkeypatch.setattr(
        "src.collectors.announcement_detail_fetcher.AnnouncementDetailFetcher.fetch_with_diagnostics",
        fake_fetch,
    )
    fetcher = EvidenceDetailFetcher(1.0, "test", 1, 1024, 2)
    item = Scholarship.from_raw(
        "test",
        "獎學金公告",
        "2026-08-01",
        "https://example.test/list",
        entry_url="https://example.test/list",
        detail_url="https://example.test/detail/1",
    )

    fetcher.fetch_with_diagnostics(item)

    assert captured == ["https://example.test/detail/1"]
