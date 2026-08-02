# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.automation.source_health_artifact import (
    build_source_health_report,
    source_health_score,
    source_health_status,
)
from src.collectors.multi_source_collector import SourceDiagnostic
from src.collectors.tun_program_watch_collector import ProgramSourceState
from src.models.source_quality import SourceRisk, SourceUrlType


def test_source_health_score_distinguishes_healthy_and_failed() -> None:
    healthy = SourceDiagnostic(
        source="正常來源",
        status="success",
        collected_count=20,
        accepted_count=18,
        duplicate_count=2,
        completeness="complete",
        pages_detected=2,
        pages_requested=2,
        pages_succeeded=2,
        raw_rows=20,
        parsed_rows=20,
        child_sources_detected=1,
        child_sources_succeeded=1,
    )
    failed = SourceDiagnostic(
        source="失敗來源",
        status="error",
        collected_count=0,
        accepted_count=0,
        duplicate_count=0,
        error="timeout",
        completeness="failed",
    )

    healthy_score = source_health_score(healthy)

    assert healthy_score == 100
    assert source_health_status(healthy_score) == "healthy"
    assert source_health_score(failed) == 0
    assert source_health_status(0) == "failed"


def test_report_keeps_url_quality_separate_from_runtime_health() -> None:
    diagnostic = SourceDiagnostic(
        source="TUN 38方案官方監測",
        status="success",
        collected_count=1,
        accepted_count=1,
        duplicate_count=0,
        completeness="complete",
        pages_detected=1,
        pages_requested=1,
        pages_succeeded=1,
        raw_rows=1,
        parsed_rows=1,
    )
    states = (
        ProgramSourceState(
            "normal",
            "尚未公告方案",
            "https://example.test/news",
            "no_current_announcement",
            source_url_type=SourceUrlType.LIST,
            update_risk=SourceRisk.LOW,
        ),
        ProgramSourceState(
            "broken",
            "結構改變方案",
            "https://example.test/old",
            "source_structure_changed",
            source_url_type=SourceUrlType.RELAY_DETAIL,
            update_risk=SourceRisk.HIGH,
        ),
    )
    collector = SimpleNamespace(
        multi_source=SimpleNamespace(
            diagnostics=[diagnostic],
            collectors=[object()],
        ),
        tun_collector=SimpleNamespace(program_states=states),
    )

    report = build_source_health_report(collector)  # type: ignore[arg-type]

    assert report["configured_source_groups"] == 1
    assert report["source_groups"][0]["health_status"] == "healthy"
    assert report["program_count"] == 2
    assert report["severe_program_count"] == 1
    assert report["severe_program_ids"] == ["broken"]
    assert report["program_states"][0]["source_url_type"] == "url_list"
    assert report["program_states"][1]["update_risk"] == "high"
