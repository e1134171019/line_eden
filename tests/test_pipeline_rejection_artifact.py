# -*- coding: utf-8 -*-

import json
from pathlib import Path
from types import SimpleNamespace

from src.automation.pipeline_rejection_artifact import write_pipeline_rejection_artifact
from src.models.scholarship import Scholarship
from src.services.scholarship_service import ExclusionRecord


def _item(title: str, *, notice_kind: str = "unknown", status: str = "not_applicable") -> Scholarship:
    item = Scholarship.from_raw(
        "source",
        title,
        "2026-08-01",
        f"https://example.test/{title}",
    )
    return Scholarship(
        **{
            **item.__dict__,
            "notice_kind": notice_kind,
            "application_status": status,
        }
    )


def test_rejection_artifact_contains_relevance_and_pipeline_stages(tmp_path: Path) -> None:
    relevance = _item("非獎助公告")
    expired = _item("過期獎學金", notice_kind="application", status="expired")
    expired = Scholarship(
        **{
            **expired.__dict__,
            "eligibility_reason": "截止日已過。",
            "exclusion_reason": "截止日已過。",
        }
    )
    result = SimpleNamespace(
        exclusions=(ExclusionRecord(relevance, "relevance", "未命中通用關鍵字"),),
        records=(SimpleNamespace(item=expired),),
    )

    path = write_pipeline_rejection_artifact(result, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    stages = {row["stage"] for row in payload["rejections"]}

    assert payload["count"] == 2
    assert stages == {"relevance", "expired"}
