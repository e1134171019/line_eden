# -*- coding: utf-8 -*-

from src.automation.source_health_artifact import SEVERE_PROGRAM_STATUSES


def test_match_failures_are_severe_in_live_contract() -> None:
    assert "fetch_failed" in SEVERE_PROGRAM_STATUSES
    assert "matcher_miss" in SEVERE_PROGRAM_STATUSES
    assert "match_ambiguous" in SEVERE_PROGRAM_STATUSES
