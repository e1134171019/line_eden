# -*- coding: utf-8 -*-

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.automation.production_acceptance_audit as audit_module
from src.models.scholarship import Scholarship


class _Collector:
    def collect(self) -> list[Scholarship]:
        return [
            Scholarship.from_raw(
                "tun-program-auden-university-talent",
                "耀登炳南大專校院優秀人才獎學金",
                "2026-08-01",
                "https://example.test/auden",
                program_id="auden-university-talent",
            ),
            Scholarship.from_raw(
                "fixture-general",
                "一般校外獎學金公告",
                "2026-08-01",
                "https://example.test/general",
            ),
        ]


class _Service:
    def __init__(self) -> None:
        self.collector = _Collector()
        self.audit_items: list[Scholarship] = []

    def audit(self) -> object:
        self.audit_items = self.collector.collect()
        return SimpleNamespace(records=[])


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


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    acceptance: _Acceptance,
    service: _Service | None = None,
) -> _Service:
    resolved_service = service or _Service()
    monkeypatch.setattr(audit_module, "ExpandedScholarshipCollector", _Collector)
    monkeypatch.setattr(audit_module, "validate_gemini_settings", lambda: None)
    monkeypatch.setattr(
        audit_module,
        "build_service",
        lambda **kwargs: resolved_service,
    )
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
    return resolved_service


def test_production_acceptance_uses_full_source_and_program_replay_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acceptance = _Acceptance()
    captured: dict[str, object] = {}
    service = _Service()
    _patch_pipeline(monkeypatch, acceptance, service)

    def _build_service(**kwargs: object) -> _Service:
        captured.update(kwargs)
        return service

    monkeypatch.setattr(audit_module, "build_service", _build_service)

    audit_module.main()

    assert captured == {
        "mode": audit_module.RunMode.AUDIT,
        "use_gemini": True,
    }
    assert [item.program_id for item in service.audit_items] == [
        "auden-university-talent"
    ]


def test_production_acceptance_audit_passes_without_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    acceptance = _Acceptance()
    _patch_pipeline(monkeypatch, acceptance)

    audit_module.main()

    assert acceptance.required is True
    output = capsys.readouterr().out
    assert "full source + 38-program semantic audit（禁止 LINE）" in output
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
