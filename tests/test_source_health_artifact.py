# -*- coding: utf-8 -*-

import json
from pathlib import Path
from types import SimpleNamespace

from src.automation.source_health_artifact import write_source_health_artifact
from src.collectors.multi_source_collector import SourceDiagnostic


def test_source_health_scores_complete_and_failed_sources(tmp_path: Path) -> None:
    collector = SimpleNamespace(
        diagnostics=[
            SourceDiagnostic(
                source="正常來源",
                status="success",
                collected_count=10,
                accepted_count=9,
                duplicate_count=1,
                completeness="complete",
                pages_requested=2,
                pages_succeeded=2,
                raw_rows=10,
                parsed_rows=9,
                rejected_rows=1,
            ),
            SourceDiagnostic(
                source="失敗來源",
                status="error",
                collected_count=0,
                accepted_count=0,
                duplicate_count=0,
                error="timeout",
                completeness="failed",
            ),
        ],
        collectors=[],
    )

    path = write_source_health_artifact(collector, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["overall_health"]["source_count"] == 2
    assert payload["overall_health"]["failed_count"] == 1
    assert payload["sources"][0]["health_status"] in {"healthy", "degraded"}
    assert payload["sources"][1]["health_score"] == 0
