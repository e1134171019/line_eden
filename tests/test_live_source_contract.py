# -*- coding: utf-8 -*-

import json
from pathlib import Path

import src.automation.live_source_contract as live_contract
from src.automation.live_source_contract import (
    LiveSourceContractResult,
    evaluate_source_states,
    write_json_report,
    write_markdown_report,
)
from src.collectors.tun_program_watch_collector import ProgramSourceState


def _state(program_id: str, status: str) -> ProgramSourceState:
    return ProgramSourceState(
        program_id=program_id,
        title=program_id,
        entry_url=f"https://example.test/{program_id}",
        status=status,
        candidate_count=2,
        top_score=95,
        reason="live|reason\nline",
    )


def _accepted_result() -> LiveSourceContractResult:
    states = tuple(_state(f"program-{index}", "matched") for index in range(38))
    return evaluate_source_states(states)


def test_live_contract_accepts_matched_and_confirmed_empty_sources() -> None:
    states = tuple(
        _state(f"program-{index}", "matched" if index % 2 else "no_current_announcement")
        for index in range(38)
    )
    result = evaluate_source_states(states)
    assert result.passed is True
    assert result.accepted_count == 38
    assert result.failed_program_ids == tuple()


def test_live_contract_rejects_every_technical_failure_status() -> None:
    states = (
        _state("fetch", "fetch_failed"),
        _state("matcher", "matcher_miss"),
        _state("structure", "source_structure_changed"),
        _state("ambiguous", "match_ambiguous"),
    )
    result = evaluate_source_states(states)
    assert result.passed is False
    assert result.accepted_count == 0
    assert result.failed_program_ids == (
        "fetch",
        "matcher",
        "structure",
        "ambiguous",
    )


def test_live_contract_requires_exactly_38_program_states() -> None:
    states = tuple(_state(f"program-{index}", "matched") for index in range(37))
    result = evaluate_source_states(states)
    assert result.passed is False
    assert result.accepted_count == 37


def test_json_report_preserves_per_program_evidence(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    write_json_report(_accepted_result(), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["total"] == 38
    assert payload["programs"][0]["entry_url"].endswith("program-0")
    assert payload["programs"][0]["candidate_count"] == 2


def test_markdown_report_escapes_table_breakers(tmp_path: Path) -> None:
    path = tmp_path / "contract.md"
    write_markdown_report(_accepted_result(), path)
    report = path.read_text(encoding="utf-8")
    assert "驗收結果：PASS" in report
    assert "live\\|reason line" in report
    assert "program-0" in report


def test_main_returns_zero_only_for_passing_contract(monkeypatch) -> None:
    accepted = _accepted_result()
    rejected = evaluate_source_states((_state("broken", "fetch_failed"),))
    monkeypatch.setattr(live_contract, "run_live_source_contract", lambda: accepted)
    assert live_contract.main() == 0
    monkeypatch.setattr(live_contract, "run_live_source_contract", lambda: rejected)
    assert live_contract.main() == 1
