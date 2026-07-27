# -*- coding: utf-8 -*-

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


# 正式排程入口必須使用專案虛擬環境與 Python 自動化模組。
def test_runner_script_uses_project_virtual_environment() -> None:
    content = (SCRIPTS_DIR / "run-scholarship-agent.ps1").read_text(encoding="utf-8")

    assert ".venv/Scripts/python.exe" in content
    assert "src.automation.scheduled_runner" in content
    assert "--use-gemini" not in content


# 安裝腳本必須防止排程重疊並以受限權限建立工作。
def test_installer_uses_safe_task_scheduler_settings() -> None:
    content = (SCRIPTS_DIR / "install-scholarship-task.ps1").read_text(encoding="utf-8")

    assert "MultipleInstances IgnoreNew" in content
    assert "RunLevel Limited" in content
    assert "StartWhenAvailable" in content
    assert "ExecutionTimeLimit" in content


# 排程必須使用目前 PowerShell host，避免只安裝 pwsh 時找不到 powershell.exe。
def test_installer_uses_current_powershell_host() -> None:
    content = (SCRIPTS_DIR / "install-scholarship-task.ps1").read_text(encoding="utf-8")

    assert "Get-Process -Id $PID" in content
    assert "-Execute $PowerShellPath" in content
    assert '-Execute "powershell.exe"' not in content


# 專案必須提供排程移除與狀態查詢腳本。
def test_management_scripts_exist() -> None:
    assert (SCRIPTS_DIR / "remove-scholarship-task.ps1").is_file()
    assert (SCRIPTS_DIR / "show-scholarship-task-status.ps1").is_file()
