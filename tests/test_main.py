# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import Any

import pytest

import main
from src.services.scholarship_service import ServiceResult


@dataclass
class FakeService:
    """記錄 CLI 呼叫模式的測試服務。"""

    calls: list[str] = field(default_factory=list)

    # 模擬一般服務執行。
    def run(self, dry_run: bool) -> ServiceResult:
        self.calls.append(f"run:{dry_run}")
        return ServiceResult([], [], 0, 0, "完成")

    # 模擬建立歷史基準。
    def initialize_baseline(self) -> ServiceResult:
        self.calls.append("initialize_baseline")
        return ServiceResult([], [], 0, 0, "完成")


# 建立不接觸網路與正式資料庫的 CLI 測試環境。
def _patch_service(monkeypatch: Any) -> FakeService:
    service = FakeService()
    monkeypatch.setattr(main, "build_service", lambda: service)
    monkeypatch.setattr(main, "print_summary", lambda _: None)
    monkeypatch.setattr(main, "print_items", lambda *_: None)
    return service


# 驗證 dry-run 不檢查 LINE 設定。
def test_dry_run_skips_line_validation(monkeypatch: Any) -> None:
    service = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--dry-run"])

    assert service.calls == ["run:True"]


# 驗證初始化基準不檢查 LINE 並呼叫正確服務方法。
def test_initialize_baseline_skips_line_validation(monkeypatch: Any) -> None:
    service = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--initialize-baseline"])

    assert service.calls == ["initialize_baseline"]


# 驗證正式模式才檢查 LINE 設定。
def test_live_mode_validates_line_settings(monkeypatch: Any) -> None:
    service = _patch_service(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: validation_calls.append("validate"))

    main.main([])

    assert validation_calls == ["validate"]
    assert service.calls == ["run:False"]


# 驗證 dry-run 與基準初始化不能同時使用。
def test_cli_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--initialize-baseline"])
