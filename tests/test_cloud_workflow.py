# -*- coding: utf-8 -*-

from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[1] / ".github/workflows/scholarship-cloud.yml"
LINE_REPORT_WORKFLOW_PATH = (
    Path(__file__).parents[1] / ".github/workflows/line-report-trigger.yml"
)


def test_cloud_workflow_uses_taiwan_0730_daily_schedule() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'cron: "30 23 * * *"' in content
    assert "TZ: Asia/Taipei" in content
    assert "github.event_name == 'schedule' && 'daily'" in content
    assert "python -m src.automation.daily_line_digest" in content


def test_cloud_workflow_requires_explicit_initialization() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "- initialize" in content
    assert "python main.py --initialize-baseline" in content
    assert "找不到雲端狀態；請先手動執行 initialize" in content


def test_cloud_workflow_uses_secrets_and_encrypted_state() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    for name in (
        "LINE_CHANNEL_ACCESS_TOKEN",
        "LINE_USER_ID",
        "GEMINI_API_KEY",
        "STUDENT_PROFILE_B64",
        "STATE_PASSPHRASE",
    ):
        assert f"secrets.{name}" in content
    assert "--symmetric --cipher-algo AES256" in content
    assert "scholarship-state.tar.gz.gpg" in content
    assert "retention-days: 90" in content


def test_cloud_workflow_restores_state_with_official_action() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "actions/download-artifact@v5" in content
    assert (
        "env.OPERATION == 'daily' || env.OPERATION == 'run' || "
        "env.OPERATION == 'report' || env.OPERATION == 'dry-run'"
    ) in content
    assert "run-id: ${{ steps.latest_state.outputs.run_id }}" in content
    assert "github-token: ${{ secrets.GITHUB_TOKEN }}" in content
    assert "gh run download" not in content
    assert "src.automation.github_artifact_state" not in content


def test_cloud_report_restores_and_saves_gemini_cache() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python -m src.automation.line_audit_report" in content
    restore_section = content.split("- name: Find latest cloud state", 1)[1].split(
        "- name: Build private profile file",
        1,
    )[0]
    state_section = content.split("- name: Encrypt updated cloud state", 1)[1].split(
        "- name: Upload encrypted cloud state",
        1,
    )[0]
    assert "env.OPERATION == 'report'" in restore_section
    assert "env.OPERATION == 'report'" in state_section
    assert "data/gemini_cache.db" in state_section


def test_cloud_report_uploads_structured_shadow_artifact() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "Upload structured shadow audit" in content
    assert "structured-shadow-audit.csv" in content
    assert "structured-shadow-audit.json" in content
    assert "structured-shadow-audit-${{ github.run_id }}" in content


def test_cloud_daily_mode_has_required_secrets_and_state() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'operation in {"initialize", "daily", "run", "report", "dry-run"}' in content
    assert 'operation in {"daily", "run", "report"}' in content
    assert 'operation in {"daily", "run", "report", "dry-run"}' in content
    assert "env.OPERATION == 'initialize' || env.OPERATION == 'daily'" in content
    assert "每日 LINE 摘要" in content


def test_cloud_workflow_has_concurrency_and_modes() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "group: scholarship-cloud-production" in content
    assert "cancel-in-progress: false" in content
    assert "python -m src.automation.daily_line_digest" in content
    assert "python main.py --use-gemini" in content
    assert "python main.py --dry-run --use-gemini" in content
    assert "- daily" in content
    assert "- report" in content


def test_cloud_test_line_is_stdlib_only() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    test_line_section = content.split("test-line)", 1)[1].split(";;", 1)[0]

    assert "import urllib.request" in test_line_section
    assert "api.line.me/v2/bot/message/push" in test_line_section
    assert "GitHub Actions 雲端測試" in test_line_section
    assert "from config import" not in test_line_section
    assert "from src." not in test_line_section
    assert "python -m src.automation.line_transport_test" not in test_line_section
    assert "TEST_MESSAGE" not in test_line_section


def test_cloud_workflows_always_clear_private_profile() -> None:
    for path in (WORKFLOW_PATH, LINE_REPORT_WORKFLOW_PATH):
        content = path.read_text(encoding="utf-8")
        cleanup_section = content.split("- name: Clear private profile", 1)[1]

        assert "if: always()" in cleanup_section
        assert "run: rm -f profile.json" in cleanup_section
