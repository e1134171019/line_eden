# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import Any

import pytest

import main
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import AuditResult, ServiceResult


@dataclass
class FakeService:
    calls: list[str] = field(default_factory=list)

    def run(self, dry_run: bool) -> ServiceResult:
        self.calls.append(f"run:{dry_run}")
        return ServiceResult([], [], 0, 0, "完成")

    def initialize_baseline(self) -> ServiceResult:
        self.calls.append("initialize_baseline")
        return ServiceResult([], [], 0, 0, "完成")

    def audit(self) -> AuditResult:
        self.calls.append("audit")
        return AuditResult([], 0, 0, 0, "完成")


def _patch_service(
    monkeypatch: Any,
) -> tuple[FakeService, list[tuple[str, bool]]]:
    service = FakeService()
    build_flags: list[tuple[str, bool]] = []

    def fake_build_full_service(
        mode: RunMode,
        use_gemini: bool = False,
    ) -> FakeService:
        build_flags.append((mode.value, use_gemini))
        return service

    def fake_build_baseline_service() -> FakeService:
        build_flags.append((RunMode.INITIALIZE_BASELINE.value, False))
        return service

    monkeypatch.setattr(main, "build_full_service", fake_build_full_service)
    monkeypatch.setattr(main, "build_baseline_service", fake_build_baseline_service)
    monkeypatch.setattr(main, "print_summary", lambda _: None)
    monkeypatch.setattr(main, "print_items", lambda *_: None)
    monkeypatch.setattr(main, "print_audit", lambda _: None)
    monkeypatch.setattr(main, "write_structured_shadow_artifacts", lambda _: ("a.csv", "a.json"))
    return service, build_flags


def test_dry_run_skips_line_validation(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--dry-run"])

    assert service.calls == ["run:True"]
    assert build_flags == [(RunMode.DRY_RUN.value, False)]


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
    assert build_flags == [(RunMode.AUDIT.value, False)]


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
    assert build_flags == [(RunMode.AUDIT.value, True)]


def test_initialize_baseline_skips_private_settings(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    monkeypatch.setattr(main, "validate_settings", lambda: pytest.fail("不應驗證 LINE"))

    main.main(["--initialize-baseline"])

    assert service.calls == ["initialize_baseline"]
    assert build_flags == [(RunMode.INITIALIZE_BASELINE.value, False)]


def test_live_mode_validates_line_settings(monkeypatch: Any) -> None:
    service, build_flags = _patch_service(monkeypatch)
    validation_calls: list[str] = []
    monkeypatch.setattr(main, "validate_settings", lambda: validation_calls.append("validate"))

    main.main([])

    assert validation_calls == ["validate"]
    assert service.calls == ["run:False"]
    assert build_flags == [(RunMode.LIVE.value, False)]


def test_cli_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--initialize-baseline"])
    with pytest.raises(SystemExit):
        main.parse_args(["--dry-run", "--audit"])


def test_initialize_baseline_rejects_gemini() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--initialize-baseline", "--use-gemini"])
