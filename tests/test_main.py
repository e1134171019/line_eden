# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import Any

import pytest

import main
from src.models.run_mode import RunMode
from src.services.scholarship_service import AuditResult, ServiceResult


@dataclass
class FakeRuntimeService:
    """記錄 runtime CLI 呼叫模式的測試服務。"""

    calls: list[str] = field(default_factory=list)

    def run(self, dry_run: bool) -> ServiceResult:
        self.calls.append(f"run:{dry_run}")
        return ServiceResult([], [], 0, 0, "完成")

    def audit(self) -> AuditResult:
        self.calls.append("audit")
        return AuditResult([], 0, 0, 0, "完成")


@dataclass
class FakeBaselineService:
    calls: list[str] = field(default_factory=list)

    def initialize_baseline(self) -> ServiceResult:
        self.calls.append("initialize_baseline")
        return ServiceResult([], [], 0, 0, "完成")


def _patch_services(
    monkeypatch: Any,
) -> tuple[
    FakeRuntimeService,
    FakeBaselineService,
    list[tuple[RunMode, bool]],
]:
    runtime = FakeRuntimeService()
    baseline = FakeBaselineService()
    build_flags: list[tuple[RunMode, bool]] = []

    def fake_build_service(
        mode: RunMode,
        use_gemini: bool = False,
    ) -> FakeRuntimeService:
        build_flags.append((mode, use_gemini))
        return runtime

    monkeypatch.setattr(main, "build_service", fake_build_service)
    monkeypatch.setattr(main, "build_baseline_service", lambda: baseline)
    monkeypatch.setattr(main, "print_summary", lambda _: None)
    monkeypatch.setattr(main, "print_items", lambda *_: None)
    monkeypatch.setattr(main, "print_audit", lambda _: None)
    monkeypatch.setattr(
        main,
        "write_structured_shadow_artifacts",
        lambda _: ("shadow.csv", "shadow.json"),
    )
    return runtime, baseline, build_flags


def test_dry_run_skips_line_validation(monkeypatch: Any) -> None:
    runtime, _, build_flags = _patch_services(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--dry-run"])

    assert runtime.calls == ["run:True"]
    assert build_flags == [(RunMode.DRY_RUN, False)]


def test_audit_skips_line_and_gemini_validation(monkeypatch: Any) -> None:
    runtime, _, build_flags = _patch_services(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))
    monkeypatch.setattr(
        main,
        "validate_gemini_settings",
        lambda: pytest.fail("未指定時不應驗證 Gemini"),
    )

    main.main(["--audit"])

    assert runtime.calls == ["audit"]
    assert build_flags == [(RunMode.AUDIT, False)]


def test_audit_with_gemini_validates_api_settings(monkeypatch: Any) -> None:
    runtime, _, build_flags = _patch_services(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))
    monkeypatch.setattr(
        main,
        "validate_gemini_settings",
        lambda: validation_calls.append("gemini"),
    )

    main.main(["--audit", "--use-gemini"])

    assert validation_calls == ["gemini"]
    assert runtime.calls == ["audit"]
    assert build_flags == [(RunMode.AUDIT, True)]


def test_initialize_baseline_uses_separate_service(monkeypatch: Any) -> None:
    _, baseline, build_flags = _patch_services(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--initialize-baseline"])

    assert baseline.calls == ["initialize_baseline"]
    assert build_flags == []


def test_live_mode_validates_line_settings(monkeypatch: Any) -> None:
    runtime, _, build_flags = _patch_services(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: validation_calls.append("validate"))

    main.main([])

    assert validation_calls == ["validate"]
    assert runtime.calls == ["run:False"]
    assert build_flags == [(RunMode.LIVE, False)]


def test_non_live_notifier_is_noop(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        main,
        "build_live_notifier",
        lambda: pytest.fail("非 live 不得建立正式 notifier"),
    )

    notifier = main.build_notifier(RunMode.AUDIT)
    notifier("不得送出")


def test_cli_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--initialize-baseline"])
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--audit"])


def test_initialize_baseline_rejects_gemini() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--initialize-baseline", "--use-gemini"])
