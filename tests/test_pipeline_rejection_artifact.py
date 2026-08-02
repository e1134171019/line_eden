# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.automation.pipeline_rejection_artifact import build_pipeline_rejections
from src.models.scholarship import Scholarship
from src.services.scholarship_service import ExclusionRecord


def _item(
    title: str,
    *,
    notice_kind: str = "application",
    application_status: str = "open",
    hard_status: str = "eligible",
    reason: str = "",
) -> Scholarship:
    base = Scholarship.from_raw(
        "test",
        title,
        "2026-08-01",
        f"https://example.test/{title}",
    )
    return Scholarship(
        **{
            **base.__dict__,
            "notice_kind": notice_kind,
            "application_status": application_status,
            "eligibility_status": hard_status,
            "eligibility_reason": reason,
            "hard_eligibility_status": hard_status,
            "hard_eligibility_reason": reason,
            "exclusion_reason": reason,
        }
    )


def test_rejection_ledger_covers_each_pipeline_stage() -> None:
    relevance = _item("一般活動")
    non_application = _item(
        "得獎名單",
        notice_kind="result",
        application_status="not_applicable",
        hard_status="not_applicable",
        reason="非申請型公告。",
    )
    expired = _item(
        "過期獎學金",
        application_status="expired",
        hard_status="not_applicable",
        reason="申請截止日已過。",
    )
    ineligible = _item(
        "限研究生獎學金",
        hard_status="ineligible",
        reason="公告限定研究生，目前學位層級不符。",
    )
    result = SimpleNamespace(
        exclusions=(ExclusionRecord(relevance, "relevance", "標題不相關。"),),
        records=(
            SimpleNamespace(item=non_application),
            SimpleNamespace(item=expired),
            SimpleNamespace(item=ineligible),
        ),
    )

    records = build_pipeline_rejections(result)  # type: ignore[arg-type]

    assert [item.stage for item in records] == [
        "relevance",
        "notice_classification",
        "application_period",
        "hard_eligibility",
    ]
    assert all(item.reason and item.reason != "未提供排除原因" for item in records)
    assert records[0].entry_url
    assert records[0].detail_url
