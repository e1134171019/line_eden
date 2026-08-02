# -*- coding: utf-8 -*-

from pathlib import Path

import pytest

import src.automation.production_acceptance_audit as audit_module


class _Collector:
    pass


class _Service:
    def __init__(self) -> None:
        self.collector = _Collector()

    def audit(self) -> object:
        return object()


class _Acceptance:
    def __init__(self, failures: tuple[str, ...] = tuple()) -> None:
        self.failures = failures
        self.required = False

    @property
    def passed(self) -> bool:
        return not self.failures

    def require_passed(self) -> None:
        self.required = True
        if self.failures:
            raise RuntimeError("Production 驗收未通過")


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, acceptance: _Acceptance) -> None:
    monkeypatch.setattr(audit_module, "ExpandedScholarshipCollector", _Collector)
    monkeypatch.setattr(audit_module, "validate_gemini_settings", lambda: None)
    monkeypatch.setattr(audit_module, "build_service", lambda **kwargs: _Service())
    monkeypatch.setattr(
        audit_module,
        "write_structured_shadow_artifacts",
        lambda result: (Path("structured.csv"), Path("structured.json")),
    )
    monkeypatch.setattr(
        audit_module,
        "build_source_health_report",
        lambda collector: {"program_states": []},
    )
    monkeypatch.setattr(
        audit_module,
        "write_source_health_artifact",
        lambda collector: Path("source-health.json"),
    )
    monkeypatch.setattr(
        audit_module,
        "write_pipeline_rejection_artifact",
        lambda result: Path("rejections.json"),
    )
    monkeypatch.setattr(
        audit_module,
        "write_production_acceptance_artifacts",
        lambda report, result: (Path("acceptance.json"), Path("acceptance.csv")),
    )
    monkeypatch.setattr(
        audit_module,
        "evaluate_release_acceptance",
        lambda report, result: acceptance,
    )


def test_production_acceptance_audit_passes_without_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    acceptance = _Acceptance()
    _patch_pipeline(monkeypatch, acceptance)

    audit_module.main()

    assert acceptance.required is True
    output = capsys.readouterr().out
    assert "Production acceptance：PASS" in output
    assert "acceptance.json" in output


def test_production_acceptance_audit_propagates_gate_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    acceptance = _Acceptance(("songliang-aid 必須為 ineligible",))
    _patch_pipeline(monkeypatch, acceptance)

    with pytest.raises(RuntimeError, match="Production 驗收未通過"):
        audit_module.main()

    output = capsys.readouterr().out
    assert "Production acceptance：FAIL" in output
    assert "songliang-aid 必須為 ineligible" in output
