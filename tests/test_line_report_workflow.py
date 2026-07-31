# -*- coding: utf-8 -*-

from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[1] / ".github/workflows/line-report-trigger.yml"


def test_line_report_uploads_structured_shadow_artifacts() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "Upload structured shadow audit" in content
    assert "line-structured-shadow-${{ github.run_id }}" in content
    assert "artifacts/structured-shadow-audit.csv" in content
    assert "artifacts/structured-shadow-audit.json" in content
