# -*- coding: utf-8 -*-

import pytest

import main
from src.runtime.run_mode import RunMode


def test_non_live_notifier_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "send_text_message",
        lambda **_: pytest.fail("非正式模式不得呼叫 LINE"),
    )

    main.build_notifier(RunMode.AUDIT)("audit")
    main.build_notifier(RunMode.DRY_RUN)("dry-run")


def test_live_and_daily_notifier_send(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    def fake_send_text_message(**kwargs: object) -> None:
        sent.append(str(kwargs["text"]))

    monkeypatch.setattr(main, "send_text_message", fake_send_text_message)

    main.build_notifier(RunMode.LIVE)("live")
    main.build_notifier(RunMode.DAILY)("daily")

    assert sent == ["live", "daily"]


def test_full_builder_rejects_baseline_mode() -> None:
    with pytest.raises(ValueError, match="build_baseline_service"):
        main.build_service(mode=RunMode.INITIALIZE_BASELINE)
