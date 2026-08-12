# -*- coding: utf-8 -*-

from dataclasses import replace

from src.automation.accepted_line_delivery import links_from_accepted_records
from src.automation.eligible_line_links import USER_CONFIRMED_ELIGIBLE_LINKS
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.models.scholarship import Scholarship
from src.services.scholarship_service import AuditRecord

AUDEN_URL = "https://www.auden.com.tw/2026scholarship/"


def _fetch_result(url: str) -> DetailFetchResult:
    diagnostic = ResourceDiagnostic(
        "source",
        url,
        url,
        "text/html",
        100,
        "html",
        "success",
        100,
    )
    return DetailFetchResult("rules", diagnostic, tuple(), 0, body_text="rules")


def _record(
    *,
    title: str,
    url: str,
    hard_status: str,
    action_status: str,
    program_id: str = "fixture-program",
) -> AuditRecord:
    item = Scholarship.from_raw(
        "fixture",
        title,
        "2026-08-12",
        url,
        program_id=program_id,
    )
    item = replace(
        item,
        detail_url=url,
        notice_kind="application",
        application_status="open",
        resolution_status="valid_application_detail",
        eligibility_status=hard_status,
        hard_eligibility_status=hard_status,
        action_status=action_status,
    )
    return AuditRecord(item, "rules", _fetch_result(url))


def test_links_from_accepted_records_selects_only_eligible_apply_candidates() -> None:
    url = "https://example.test/eligible"
    records = [
        _record(
            title="符合方案",
            url=url,
            hard_status="eligible",
            action_status="apply_candidate",
        ),
        _record(
            title="符合方案重複公告",
            url=url,
            hard_status="eligible",
            action_status="apply_candidate",
        ),
        _record(
            title="待確認方案",
            url="https://example.test/review",
            hard_status="review",
            action_status="manual_review",
        ),
        _record(
            title="不符合方案",
            url="https://example.test/ineligible",
            hard_status="ineligible",
            action_status="reject",
        ),
    ]

    links = links_from_accepted_records(records)

    assert [(link.title, link.url) for link in links] == [("符合方案", url)]


def test_formal_selection_does_not_reintroduce_static_confirmed_auden() -> None:
    assert any(link.url == AUDEN_URL for link in USER_CONFIRMED_ELIGIBLE_LINKS)
    records = [
        _record(
            title="2026耀登炳南大專校院優秀人才獎學金",
            url=AUDEN_URL,
            hard_status="ineligible",
            action_status="reject",
            program_id="auden-university-talent",
        )
    ]

    links = links_from_accepted_records(records)

    assert all(link.url != AUDEN_URL for link in links)
