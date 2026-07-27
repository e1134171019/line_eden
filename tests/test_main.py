# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import Any

import pytest

import main
from src.services.scholarship_service import AuditResult, ServiceResult


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

    # 模擬全部公告稽核。
    def audit(self) -> AuditResult:
        self.calls.append("audit")
        return AuditResult([], 0, 0, 0, "完成")


# 建立不接觸網路與正式資料庫的 CLI 測試環境。
def _patch_service(
    monkeypatch: Any,
) -> tuple[FakeService, list[tuple[bool, bool]]]:
    service = FakeService()
    build_flags: list[tuple[bool, bool]] = []

    # 記錄 CLI 是否要求載入私密背景與 Gemini。
    def fake_build_service(
        profile_required: bool = True,
        use_gemini: bool = False,
    ) -> FakeService:
        build_flags.append((profile_required, use_gemini))
        return service

    monkeypatch.setattr(main, "build_service", fake_build_service)
    monkeypatch.setattr(main, "print_summary", lambda _: None)
    monkeypatch.setattr(main, "print_items", lambda *_: None)
    monkeypatch.setattr(main, "print_audit", lambda _: None)
    return service, build_flags


# 驗證 dry-run 不檢查 LINE，但會載入個人背景。
def test_dry_run_skips_line_validation(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--dry-run"])

    assert service.calls == ["run:True"]
    assert build_flags == [(True, False)]


# 驗證 audit 預設不檢查 LINE，也不啟用 Gemini。
def test_audit_skips_line_and_gemini_validation(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))
    monkeypatch.setattr(
        main,
        "validate_gemini_settings",
        lambda: pytest.fail("未指定時不應驗證 Gemini"),
    )

    main.main(["--audit"])

    assert service.calls == ["audit"]
    assert build_flags == [(True, False)]


# 驗證明確指定 Gemini 時會驗證 API 設定並注入備援。
def test_audit_with_gemini_validates_api_settings(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))
    monkeypatch.setattr(
        main,
        "validate_gemini_settings",
        lambda: validation_calls.append("gemini"),
    )

    main.main(["--audit", "--use-gemini"])

    assert validation_calls == ["gemini"]
    assert service.calls == ["audit"]
    assert build_flags == [(True, True)]


# 驗證初始化基準不檢查 LINE，也不載入個人背景。
def test_initialize_baseline_skips_private_settings(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--initialize-baseline"])

    assert service.calls == ["initialize_baseline"]
    assert build_flags == [(False, False)]


# 驗證正式模式檢查 LINE 並載入個人背景。
def test_live_mode_validates_line_settings(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: validation_calls.append("validate"))

    main.main([])

    assert validation_calls == ["validate"]
    assert service.calls == ["run:False"]
    assert build_flags == [(True, False)]


# 驗證三種安全模式不能同時使用。
def test_cli_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--initialize-baseline"])
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--audit"])


# 驗證建立基準時不能額外消耗 Gemini。
def test_initialize_baseline_rejects_gemini() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--initialize-baseline", "--use-gemini"])
