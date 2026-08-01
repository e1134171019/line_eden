# -*- coding: utf-8 -*-

import pytest

from src.notifiers.notification_dispatcher import (
    CallableNotificationChannel,
    NotificationFanout,
)


def test_notification_fanout_routes_only_to_selected_channel() -> None:
    line_messages: list[str] = []
    email_messages: list[str] = []
    dispatcher = NotificationFanout(
        (
            CallableNotificationChannel("line", line_messages.append),
            CallableNotificationChannel("email", email_messages.append),
        )
    )

    dispatcher.send_text("email", "獎學金通知")

    assert dispatcher.channel_ids() == ("line", "email")
    assert line_messages == []
    assert email_messages == ["獎學金通知"]


def test_notification_fanout_rejects_duplicate_or_unknown_channel() -> None:
    channel = CallableNotificationChannel("same", lambda _: None)

    with pytest.raises(ValueError, match="不得重複"):
        NotificationFanout((channel, channel))

    dispatcher = NotificationFanout((channel,))
    with pytest.raises(KeyError, match="missing"):
        dispatcher.send_text("missing", "通知")


def test_notification_fanout_rejects_channel_id_with_padding() -> None:
    with pytest.raises(ValueError, match="首尾空白"):
        NotificationFanout((CallableNotificationChannel(" line ", lambda _: None),))
