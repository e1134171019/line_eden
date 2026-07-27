# -*- coding: utf-8 -*-

from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[1] / ".github/workflows/scholarship-cloud.yml"


# 雲端排程必須在台灣 07:30 對應的 UTC 23:30 執行。
def test_cloud_workflow_uses_taiwan_0730_schedule() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'cron: "30 23 * * *"' in content
    assert "TZ: Asia/Taipei" in content


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


# 狀態還原改用 GitHub CLI，避免自製 redirect 下載器失敗。
def test_cloud_workflow_restores_state_with_github_cli() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "gh api" in content
    assert "gh run download" in content
    assert "--name scholarship-agent-state" in content
    assert "src.automation.github_artifact_state" not in content


# 正式排程必須防止同時執行，且保留正式、報告與 dry-run 模式。
def test_cloud_workflow_has_concurrency_and_modes() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "group: scholarship-cloud-production" in content
    assert "cancel-in-progress: false" in content
    assert "python main.py --use-gemini" in content
    assert "python main.py --dry-run --use-gemini" in content
    assert "- report" in content
    assert "獎學金真實檢查報告" in content
    assert "GitHub Actions 雲端測試" in content
