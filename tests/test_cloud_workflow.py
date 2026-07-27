# -*- coding: utf-8 -*-

from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[1] / ".github/workflows/scholarship-cloud.yml"


# 雲端排程必須在台灣 07:30 對應的 UTC 23:30 執行，並固定使用 daily 模式。
def test_cloud_workflow_uses_taiwan_0730_daily_schedule() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'cron: "30 23 * * *"' in content
    assert "TZ: Asia/Taipei" in content
    assert "github.event_name == 'schedule' && 'daily'" in content
    assert "python -m src.automation.daily_line_digest" in content


# 第一次必須手動初始化，正式排程缺少狀態時不得自行 baseline。
def test_cloud_workflow_requires_explicit_initialization() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "- initialize" in content
    assert "python main.py --initialize-baseline" in content
    assert "找不到雲端狀態；請先手動執行 initialize" in content


# 個資與 API 金鑰必須來自 Secrets，狀態 artifact 必須加密後保存。
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


# daily、run 與 dry-run 的狀態還原使用 GitHub 官方 download-artifact action。
def test_cloud_workflow_restores_state_with_official_action() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "actions/download-artifact@v5" in content
    assert "env.OPERATION == 'daily' || env.OPERATION == 'run' || env.OPERATION == 'dry-run'" in content
    assert "run-id: ${{ steps.latest_state.outputs.run_id }}" in content
    assert "github-token: ${{ secrets.GITHUB_TOKEN }}" in content
    assert "gh run download" not in content
    assert "src.automation.github_artifact_state" not in content


# report 必須直接稽核真實資料，不得依賴雲端 SQLite 還原或保存狀態。
def test_cloud_report_is_independent_from_cloud_state() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python -m src.automation.line_audit_report" in content
    restore_section = content.split("- name: Find latest cloud state", 1)[1].split(
        "- name: Build private profile file", 1
    )[0]
    state_section = content.split("- name: Encrypt updated cloud state", 1)[1].split(
        "- name: Upload encrypted cloud state", 1
    )[0]
    assert "env.OPERATION == 'report'" not in restore_section
    assert "env.OPERATION == 'report'" not in state_section


# daily 必須使用 LINE、Gemini、學生背景與加密狀態，並於執行後保存狀態。
def test_cloud_daily_mode_has_required_secrets_and_state() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'operation in {"initialize", "daily", "run", "dry-run"}' in content
    assert 'operation in {"daily", "run", "report"}' in content
    assert 'operation in {"daily", "run", "report", "dry-run"}' in content
    assert "env.OPERATION == 'initialize' || env.OPERATION == 'daily'" in content
    assert "每日 LINE 摘要" in content


# 正式排程必須防止同時執行，且保留 daily、正式、報告與 dry-run 模式。
def test_cloud_workflow_has_concurrency_and_modes() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "group: scholarship-cloud-production" in content
    assert "cancel-in-progress: false" in content
    assert "python -m src.automation.daily_line_digest" in content
    assert "python main.py --use-gemini" in content
    assert "python main.py --dry-run --use-gemini" in content
    assert "- daily" in content
    assert "- report" in content
    assert "GitHub Actions 雲端測試" in content
