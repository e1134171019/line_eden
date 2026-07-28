# -*- coding: utf-8 -*-

import pytest

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.evidence_detail_fetcher import EvidenceDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
    RULES_STATUS_RESOLVED,
)
from src.models.scholarship import Scholarship


def _result() -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.com/notice",
        "https://example.com/notice",
        "text/html",
        100,
        "html",
        "success",
        20,
    )
    rules = ExtractedAttachment(
        "https://example.com/rules.pdf",
        "https://example.com/rules.pdf",
        "附件一",
        "generic_attachment",
        "scholarship_rules",
        "pdf",
        "success",
        "申請資格限電子工程相關科系。",
    )
    supporting = ExtractedAttachment(
        "https://example.com/form.pdf",
        "https://example.com/form.pdf",
        "聲明書",
        "supporting_document",
        "supporting_document",
        "pdf",
        "success",
        "本人聲明以上資料正確。",
    )
    return DetailFetchResult(
        "舊格式【附件內容】不應作為邊界",
        source,
        tuple(),
        2,
        body_text="正文提到請參閱附件內容，但這只是一般文字。",
        extracted_attachments=(rules, supporting),
        rules_status=RULES_STATUS_RESOLVED,
    )


def test_eligibility_text_uses_only_body_and_confirmed_rules() -> None:
    text = _result().eligibility_text()

    assert "正文提到請參閱附件內容" in text
    assert "申請資格限電子工程相關科系" in text
    assert "本人聲明" not in text
    assert "舊格式【附件內容】" not in text


def test_evidence_fetcher_replaces_legacy_combined_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _result()
    monkeypatch.setattr(
        AnnouncementDetailFetcher,
        "fetch_with_diagnostics",
        lambda self, scholarship: expected,
    )
    fetcher = EvidenceDetailFetcher(10.0, "test", 3, 1024, 2)
    item = Scholarship.from_raw(
        "test",
        "測試獎學金",
        "2026-07-28",
        "https://example.com/notice",
    )

    actual = fetcher.fetch_with_diagnostics(item)

    assert actual.text == expected.eligibility_text()
    assert "本人聲明" not in actual.text
