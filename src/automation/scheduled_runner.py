# -*- coding: utf-8 -*-

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable, Iterator

from config import (
    AUTOMATION_LOCK_FILENAME,
    AUTOMATION_LOG_DIRNAME,
    AUTOMATION_STALE_LOCK_HOURS,
    AUTOMATION_STATUS_FILENAME,
    BASE_DIR,
)

SUMMARY_LABELS = {
    "蒐集公告數量": "collected",
    "適合且待通知": "pending",
    "明確適合": "eligible",
    "資格待確認": "review",
    "明確不符合": "ineligible",
    "本次通知數量": "notified",
    "Gemini 生成呼叫": "gemini_calls",
    "Gemini 快取命中": "gemini_cache_hits",
}

Runner = Callable[..., subprocess.CompletedProcess[str]]
NowProvider = Callable[[], datetime]


class AlreadyRunningError(RuntimeError):
    """另一個排程程序仍持有執行鎖。"""


# 執行正式 Scholarship Agent，保存日誌與最後執行狀態。
def run_scheduled_agent(
    project_dir: Path = BASE_DIR,
    use_gemini: bool = True,
    runner: Runner = subprocess.run,
    now_provider: NowProvider | None = None,
) -> int:
    project_dir = project_dir.resolve()
    data_dir = project_dir / "data"
    log_dir = project_dir / AUTOMATION_LOG_DIRNAME
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / AUTOMATION_LOCK_FILENAME
    try:
        with execution_lock(lock_path, AUTOMATION_STALE_LOCK_HOURS):
            return _run_locked(project_dir, data_dir, log_dir, use_gemini, runner, now_provider)
    except AlreadyRunningError:
        print("Scholarship Agent 已在執行，本次排程略過。")
        return 0


# 持有排程鎖期間執行子程序並原子更新 last_run.json。
def _run_locked(
    project_dir: Path,
    data_dir: Path,
    log_dir: Path,
    use_gemini: bool,
    runner: Runner,
    now_provider: NowProvider | None,
) -> int:
    now = now_provider or _local_now
    started_at = now()
    log_path = log_dir / f"run-{started_at:%Y%m%d-%H%M%S}.log"
    status_path = data_dir / AUTOMATION_STATUS_FILENAME
    command = [sys.executable, str(project_dir / "main.py")]
    if use_gemini:
        command.append("--use-gemini")
    _write_status(status_path, _running_status(started_at, log_path, project_dir, use_gemini))
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    try:
        completed = runner(
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        finished_at = now()
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        _write_log(log_path, started_at, finished_at, command, stdout, stderr)
        status = _completed_status(
            started_at,
            finished_at,
            completed.returncode,
            log_path,
            project_dir,
            use_gemini,
            stdout,
        )
        _write_status(status_path, status)
        _print_child_output(stdout, stderr)
        return completed.returncode
    except Exception as error:
        finished_at = now()
        message = f"{type(error).__name__}: {error}"
        _write_log(log_path, started_at, finished_at, command, "", message)
        status = _failed_status(
            started_at,
            finished_at,
            log_path,
            project_dir,
            use_gemini,
            message,
        )
        _write_status(status_path, status)
        print(message, file=sys.stderr)
        return 1


# 使用原子建立檔案取得鎖；超過時限的殘留鎖可安全清除。
@contextmanager
def execution_lock(lock_path: Path, stale_hours: int) -> Iterator[None]:
    _acquire_lock(lock_path, stale_hours)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# 以 O_EXCL 防止兩個排程同時建立同一把鎖。
def _acquire_lock(lock_path: Path, stale_hours: int) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_stale(lock_path, stale_hours):
                lock_path.unlink(missing_ok=True)
                continue
            raise AlreadyRunningError(str(lock_path)) from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            lock_file.write(
                json.dumps(
                    {"pid": os.getpid(), "created_at": _local_now().isoformat()},
                    ensure_ascii=False,
                )
            )
        return
    raise AlreadyRunningError(str(lock_path))


# 依檔案修改時間判斷前次異常中斷留下的鎖是否已失效。
def _lock_is_stale(lock_path: Path, stale_hours: int) -> bool:
    age_seconds = time.time() - lock_path.stat().st_mtime
    return age_seconds > stale_hours * 60 * 60


# 建立執行中的健康狀態。
def _running_status(
    started_at: datetime,
    log_path: Path,
    project_dir: Path,
    use_gemini: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "running",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "exit_code": None,
        "use_gemini": use_gemini,
        "log_file": _relative_path(log_path, project_dir),
        "summary": {},
    }


# 建立成功或失敗完成狀態與命令列摘要數字。
def _completed_status(
    started_at: datetime,
    finished_at: datetime,
    exit_code: int,
    log_path: Path,
    project_dir: Path,
    use_gemini: bool,
    stdout: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "success" if exit_code == 0 else "failed",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": max((finished_at - started_at).total_seconds(), 0),
        "exit_code": exit_code,
        "use_gemini": use_gemini,
        "log_file": _relative_path(log_path, project_dir),
        "summary": parse_summary(stdout),
    }


# 建立啟動器自身例外的失敗狀態。
def _failed_status(
    started_at: datetime,
    finished_at: datetime,
    log_path: Path,
    project_dir: Path,
    use_gemini: bool,
    error: str,
) -> dict[str, object]:
    status = _completed_status(
        started_at,
        finished_at,
        1,
        log_path,
        project_dir,
        use_gemini,
        "",
    )
    status["error"] = error
    return status


# 從既有 main.py 中文摘要擷取健康狀態數字。
def parse_summary(output: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for line in output.splitlines():
        label, separator, value = line.partition("：")
        key = SUMMARY_LABELS.get(label.strip())
        if not separator or not key:
            continue
        try:
            summary[key] = int(value.strip())
        except ValueError:
            continue
    return summary


# 將子程序標準輸出及錯誤輸出保存到單次執行日誌。
def _write_log(
    log_path: Path,
    started_at: datetime,
    finished_at: datetime,
    command: list[str],
    stdout: str,
    stderr: str,
) -> None:
    command_text = " ".join(_display_command(command))
    content = [
        f"started_at={started_at.isoformat()}",
        f"finished_at={finished_at.isoformat()}",
        f"command={command_text}",
        "",
        "[stdout]",
        stdout.rstrip(),
        "",
        "[stderr]",
        stderr.rstrip(),
        "",
    ]
    log_path.write_text("\n".join(content), encoding="utf-8")


# 以暫存檔替換方式避免 last_run.json 寫到一半中斷。
def _write_status(status_path: Path, status: dict[str, object]) -> None:
    temporary = status_path.with_name(f"{status_path.name}.tmp")
    temporary.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(status_path)


# 將日誌路徑轉成相對專案路徑，避免寫死本機位置。
def _relative_path(path: Path, project_dir: Path) -> str:
    return path.relative_to(project_dir).as_posix()


# 日誌只顯示虛擬環境 Python 名稱與 main.py 參數。
def _display_command(command: list[str]) -> list[str]:
    return [Path(command[0]).name, Path(command[1]).name, *command[2:]]


# 排程手動測試時仍將正式程式輸出顯示在目前終端。
def _print_child_output(stdout: str, stderr: str) -> None:
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)


# 取得含本機時區的目前時間。
def _local_now() -> datetime:
    return datetime.now().astimezone()


# 解析自動排程啟動器參數。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scholarship Agent Windows 排程啟動器")
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="正式執行但不啟用 Gemini 備援",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=BASE_DIR,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


# 執行排程入口並將子程序結果回傳給 Windows 工作排程器。
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_scheduled_agent(args.project_dir, use_gemini=not args.no_gemini)


if __name__ == "__main__":
    raise SystemExit(main())
