# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import main
from src.cli.run_mode import RunMode
from src.notifiers.noop_notifier import discard_notification
from src.services.scholarship_service import AuditResult, ServiceResult


@dataclass
class FakeFullService:
    """記錄完整服務的 CLI 呼叫模式。"""

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
    FakeFullService,
    FakeBaselineService,
    list[tuple[RunMode, bool]],
]:
    full_service = FakeFullService()
    baseline_service = FakeBaselineService()
    full_builds: list[tuple[RunMode, bool]] = []

    def fake_build_full_service(
        mode: RunMode,
        *,
        use_gemini: bool = False,
    ) -> FakeFullService:
        full_builds.append((mode, use_gemini))
        return full_service

    monkeypatch.setattr(main, "build_full_service", fake_build_full_service)
    monkeypatch.setattr(main, "build_baseline_service", lambda: baseline_service)
    monkeypatch.setattr(main, "print_service_result", lambda _: None)
    monkeypatch.setattr(main, "print_audit_result", lambda _: None)
    monkeypatch.setattr(
        main,
        "write_structured_shadow_artifacts",
        lambda _: (Path("shadow.csv"), Path("shadow.json")),
    )
    return full_service, baseline_service, full_builds


def test_dry_run_skips_line_validation(monkeypatch: Any) -> None:
    service, _, builds = _patch_services(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--dry-run"])

    assert service.calls == ["run:True"]
    assert builds == [(RunMode.DRY_RUN, False)]


def test_audit_skips_line_and_gemini_validation(monkeypatch: Any) -> None:
    service, _, builds = _patch_services(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))
    monkeypatch.setattr(
        main,
        "validate_gemini_settings",
        lambda: pytest.fail("未指定時不應驗證 Gemini"),
    )

    main.main(["--audit"])

    assert service.calls == ["audit"]
    assert builds == [(RunMode.AUDIT, False)]


def test_audit_with_gemini_validates_api_settings(monkeypatch: Any) -> None:
    service, _, builds = _patch_services(monkeypatch)
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
    assert builds == [(RunMode.AUDIT, True)]


def test_initialize_baseline_uses_dedicated_service(monkeypatch: Any) -> None:
    full_service, baseline_service, builds = _patch_services(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--initialize-baseline"])

    assert baseline_service.calls == ["initialize_baseline"]
    assert full_service.calls == []
    assert builds == []


def test_live_mode_validates_line_settings(monkeypatch: Any) -> None:
    service, _, builds = _patch_services(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: validation_calls.append("validate"))

    main.main([])

    assert validation_calls == ["validate"]
    assert service.calls == ["run:False"]
    assert builds == [(RunMode.LIVE, False)]


def test_cli_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--initialize-baseline"])
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--audit"])


def test_parse_args_returns_explicit_run_mode() -> None:
    assert main.parse_args([]).mode is RunMode.LIVE
    assert main.parse_args(["--dry-run"]).mode is RunMode.DRY_RUN
    assert main.parse_args(["--audit"]).mode is RunMode.AUDIT
    assert main.parse_args(["--initialize-baseline"]).mode is RunMode.INITIALIZE_BASELINE


def test_initialize_baseline_rejects_gemini() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--initialize-baseline", "--use-gemini"])


def test_non_live_modes_use_noop_notifier(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        main,
        "build_live_notifier",
        lambda: pytest.fail("非 live 模式不得建立正式 notifier"),
    )

    assert main.build_notifier(RunMode.DRY_RUN) is discard_notification
    assert main.build_notifier(RunMode.AUDIT) is discard_notification
