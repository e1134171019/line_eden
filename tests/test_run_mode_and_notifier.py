# -*- coding: utf-8 -*-

import pytest

import main
from src.notifiers.notification_dispatcher import CallableNotificationChannel
from src.runtime.run_mode import RunMode


def test_non_live_notifier_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "send_text_message",
        lambda **_: pytest.fail("非正式模式不得呼叫 LINE"),
    )

    assert main.build_notifier(RunMode.AUDIT).channel_ids() == tuple()
    assert main.build_notifier(RunMode.DRY_RUN).channel_ids() == tuple()


def test_live_and_daily_notifier_send(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    def fake_send_text_message(**kwargs: object) -> None:
        sent.append(str(kwargs["text"]))

    monkeypatch.setattr(main, "send_text_message", fake_send_text_message)

    main.build_notifier(RunMode.LIVE).send_text("line", "live")
    main.build_notifier(RunMode.DAILY).send_text("line", "daily")

    assert sent == ["live", "daily"]


def test_live_notifier_adds_optional_apprise_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    loaded: list[tuple[tuple[str, ...], str]] = []

    def fake_load_apprise_channels(
        urls: tuple[str, ...],
        title: str,
    ) -> tuple[CallableNotificationChannel, ...]:
        loaded.append((urls, title))
        return (CallableNotificationChannel("apprise-test", sent.append),)

    monkeypatch.setattr(main, "APPRISE_URLS", ("discord://private",))
    monkeypatch.setattr(main, "load_apprise_channels", fake_load_apprise_channels)

    notifier = main.build_notifier(RunMode.LIVE)
    notifier.send_text("apprise-test", "extra")

    assert notifier.channel_ids() == ("line", "apprise-test")
    assert loaded == [(("discord://private",), "Scholarship Agent")]
    assert sent == ["extra"]


def test_full_builder_rejects_baseline_mode() -> None:
    with pytest.raises(ValueError, match="build_baseline_service"):
        main.build_service(mode=RunMode.INITIALIZE_BASELINE)
