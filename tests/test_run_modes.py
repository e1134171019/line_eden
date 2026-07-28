# -*- coding: utf-8 -*-

from argparse import Namespace

from main import build_notifier, parse_mode
from src.runtime.run_mode import RunMode


def _args(**overrides: bool) -> Namespace:
    values = {
        "dry_run": False,
        "audit": False,
        "initialize_baseline": False,
        "use_gemini": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_parse_mode_defaults_to_live() -> None:
    assert parse_mode(_args()) is RunMode.LIVE


def test_parse_mode_is_explicit_for_non_live_modes() -> None:
    assert parse_mode(_args(dry_run=True)) is RunMode.DRY_RUN
    assert parse_mode(_args(audit=True)) is RunMode.AUDIT
    assert parse_mode(_args(initialize_baseline=True)) is RunMode.INITIALIZE_BASELINE


def test_non_live_notifier_is_noop() -> None:
    notifier = build_notifier(RunMode.AUDIT)
    notifier("不得傳送")
