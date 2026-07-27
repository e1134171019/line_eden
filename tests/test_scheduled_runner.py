# -*- coding: utf-8 -*-

from collections.abc import Callable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from config import AUTOMATION_LOCK_FILENAME, AUTOMATION_STATUS_FILENAME
from src.automation.scheduled_runner import parse_summary, run_scheduled_agent


# 建立固定時刻供開始與結束狀態使用。
def _now_provider() -> Callable[[], datetime]:
    moments = iter(
        (
            datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 28, 8, 0, 2, tzinfo=timezone.utc),
        )
    )
    return lambda: next(moments)


# 成功執行時應建立日誌、健康狀態並移除執行鎖。
def test_scheduled_runner_records_success(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")

    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        output = (
            "蒐集公告數量：81\n"
            "適合且待通知：1\n"
            "明確適合：1\n"
            "資格待確認：0\n"
            "明確不符合：0\n"
            "本次通知數量：1\n"
            "Gemini 生成呼叫：0\n"
            "Gemini 快取命中：1\n"
        )
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    exit_code = run_scheduled_agent(
        tmp_path,
        use_gemini=True,
        runner=fake_runner,
        now_provider=_now_provider(),
    )

    status_path = tmp_path / "data" / AUTOMATION_STATUS_FILENAME
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert status["status"] == "success"
    assert status["summary"]["collected"] == 81
    assert status["summary"]["notified"] == 1
    assert status["use_gemini"] is True
    assert (tmp_path / status["log_file"]).exists()
    assert not (tmp_path / "data" / AUTOMATION_LOCK_FILENAME).exists()


# 子程序失敗時應保留非零結果與錯誤輸出日誌。
def test_scheduled_runner_records_failed_process(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")

    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="LINE API error")

    exit_code = run_scheduled_agent(
        tmp_path,
        runner=fake_runner,
        now_provider=_now_provider(),
    )

    status = json.loads(
        (tmp_path / "data" / AUTOMATION_STATUS_FILENAME).read_text(encoding="utf-8")
    )
    log_text = (tmp_path / status["log_file"]).read_text(encoding="utf-8")
    assert exit_code == 2
    assert status["status"] == "failed"
    assert status["exit_code"] == 2
    assert "LINE API error" in log_text


# 新鮮的執行鎖存在時不得啟動第二個子程序。
def test_scheduled_runner_skips_when_lock_is_active(tmp_path: Path) -> None:
    lock_path = tmp_path / "data" / AUTOMATION_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("{}", encoding="utf-8")
    calls = 0

    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    exit_code = run_scheduled_agent(tmp_path, runner=fake_runner)

    assert exit_code == 0
    assert calls == 0
    assert lock_path.exists()


# 超過六小時的殘留鎖可被清除並重新執行。
def test_scheduled_runner_replaces_stale_lock(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    lock_path = tmp_path / "data" / AUTOMATION_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("{}", encoding="utf-8")
    stale_time = lock_path.stat().st_mtime - 7 * 60 * 60
    os.utime(lock_path, (stale_time, stale_time))

    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="蒐集公告數量：80\n", stderr="")

    exit_code = run_scheduled_agent(
        tmp_path,
        runner=fake_runner,
        now_provider=_now_provider(),
    )

    assert exit_code == 0
    assert not lock_path.exists()


# 中文摘要只擷取已知且可轉成整數的欄位。
def test_parse_summary_ignores_unknown_and_invalid_values() -> None:
    output = "蒐集公告數量：80\n明確適合：無\n其他欄位：9\n本次通知數量：0\n"

    assert parse_summary(output) == {"collected": 80, "notified": 0}
