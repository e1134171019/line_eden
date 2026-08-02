# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
)
from src.models.announcement_revision import (
    build_announcement_id,
    build_revision_hash,
    canonicalize_announcement_url,
)
from src.models.scholarship import Scholarship


def _result(body: str, rules: str = "") -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.test/detail?utm_source=line",
        "https://example.test/detail",
        "text/html",
        len(body.encode()),
        "html",
        "success",
        len(body),
        extraction_policy_hash="policy-v1",
        selected_selector="main",
    )
    attachments = (
        ExtractedAttachment(
            "https://example.test/rules.pdf",
            "https://example.test/rules.pdf",
            "申請辦法",
            "rules",
            "scholarship_rules",
            "pdf",
            "success",
            rules,
        ),
    ) if rules else tuple()
    return DetailFetchResult(
        body,
        source,
        tuple(),
        len(attachments),
        body_text=body,
        extracted_attachments=attachments,
        rules_status="resolved" if rules else "not_required",
    )


def test_url_canonicalization_removes_tracking_and_fragment() -> None:
    value = canonicalize_announcement_url(
        "HTTPS://Example.TEST//detail/?utm_source=line&b=2&a=1#section"
    )

    assert value == "https://example.test/detail?a=1&b=2"


def test_known_program_id_stabilizes_announcement_identity() -> None:
    first = Scholarship.from_raw(
        "tun-program-auden-university-talent",
        "2025耀登人才獎學金",
        "2025-07-01",
        "https://example.test/2025",
        program_id="auden-university-talent",
    )
    second = Scholarship.from_raw(
        "tun-program-auden-university-talent",
        "2026耀登人才獎學金",
        "2026-07-01",
        "https://example.test/2026",
        program_id="auden-university-talent",
    )

    assert build_announcement_id(first) == build_announcement_id(second)


def test_revision_ignores_view_count_but_detects_rules_change() -> None:
    item = Scholarship.from_raw(
        "test",
        "能源獎學金",
        "2026-08-01",
        "https://example.test/detail",
    )
    first = build_revision_hash(
        item,
        _result("申請資格：大專生。瀏覽人次：123", "成績門檻八十分。"),
    )
    same = build_revision_hash(
        item,
        _result("申請資格：大專生。瀏覽人次：999", "成績門檻八十分。"),
    )
    changed = build_revision_hash(
        item,
        _result("申請資格：大專生。", "成績門檻八十五分。"),
    )

    assert first == same
    assert changed != first
