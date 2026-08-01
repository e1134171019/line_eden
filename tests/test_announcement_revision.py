# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
)
from src.models.announcement_revision import (
    build_announcement_id,
    build_revision_hash,
    normalize_announcement_url,
)


def _result(body: str, attachments: tuple[str, ...] = tuple()) -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.test/item",
        "https://example.test/item",
        "text/html",
        len(body.encode("utf-8")),
        "html",
        "success",
        len(body),
    )
    extracted = tuple(
        ExtractedAttachment(
            f"https://example.test/{index}.pdf",
            f"https://example.test/{index}.pdf",
            "辦法",
            "rules",
            "scholarship_rules",
            "pdf",
            "success",
            text,
        )
        for index, text in enumerate(attachments, start=1)
    )
    return DetailFetchResult(
        body,
        source,
        tuple(),
        len(extracted),
        body_text=body,
        extracted_attachments=extracted,
        rules_status="resolved",
    )


def test_tracking_parameters_and_query_order_do_not_change_announcement_id() -> None:
    first = "https://Example.test/news/88/?b=2&a=1&utm_source=line#top"
    second = "https://example.test/news/88?a=1&b=2"

    assert normalize_announcement_url(first) == normalize_announcement_url(second)
    assert build_announcement_id("source", first) == build_announcement_id("source", second)


def test_whitespace_and_attachment_order_do_not_change_revision() -> None:
    first = _result("申請資格 為 大專生", ("附件甲 資格", "附件乙 方式"))
    second = _result("  申請資格   為 大專生  ", ("附件乙 方式", "附件甲 資格"))

    assert build_revision_hash(first) == build_revision_hash(second)


def test_substantive_body_change_changes_revision() -> None:
    first = _result("截止日期為9月30日。")
    second = _result("截止日期延長至10月15日。")

    assert build_revision_hash(first) != build_revision_hash(second)
