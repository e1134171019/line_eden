# -*- coding: utf-8 -*-

from pathlib import Path


# Production LINE workflow 必須使用完整 bundle 並保留四個 audit artifacts。
def test_line_report_workflow_runs_complete_audit_bundle() -> None:
    content = Path(".github/workflows/line-report-trigger.yml").read_text(
        encoding="utf-8"
    )

    assert "python -m src.automation.line_audit_bundle" in content
    assert "- name: Upload structured shadow audit" in content
    assert "artifacts/structured-shadow-audit.csv" in content
    assert "artifacts/structured-shadow-audit.json" in content
    assert "artifacts/source-health.json" in content
    assert "artifacts/pipeline-rejections.json" in content
    assert "rm -f profile.json" in content


# 每週 live contract 不依賴 profile、Gemini 或 LINE Secrets。
def test_source_contract_workflow_is_independent_and_uploads_health() -> None:
    content = Path(".github/workflows/source-contract.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in content
    assert 'cron: "20 23 * * 0"' in content
    assert "python -m src.automation.source_contract_report" in content
    assert "artifacts/source-health.json" in content
    assert "LINE_CHANNEL_ACCESS_TOKEN" not in content
    assert "GEMINI_API_KEY" not in content
    assert "STUDENT_PROFILE_B64" not in content
