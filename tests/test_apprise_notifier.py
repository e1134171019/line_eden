# -*- coding: utf-8 -*-

import pytest

from src.notifiers.apprise_notifier import (
    AppriseNotificationChannel,
    build_apprise_channel_id,
    load_apprise_channels,
)


class FakeAppriseClient:
    """保存 Apprise adapter 呼叫並回傳指定結果。"""

    def __init__(self, is_valid: bool = True, is_sent: bool | None = True) -> None:
        self.is_valid = is_valid
        self.is_sent = is_sent
        self.urls: list[str] = []
        self.messages: list[tuple[str, str]] = []

    def add(self, servers: str) -> bool:
        self.urls.append(servers)
        return self.is_valid

    def notify(self, *, body: str, title: str) -> bool | None:
        self.messages.append((title, body))
        return self.is_sent


def test_load_apprise_channels_creates_one_retry_boundary_per_url() -> None:
    clients: list[FakeAppriseClient] = []

    def load_client() -> FakeAppriseClient:
        client = FakeAppriseClient()
        clients.append(client)
        return client

    urls = ("discord://secret-a", "tgram://secret-b")
    channels = load_apprise_channels(urls, "Scholarship Agent", load_client)

    channels[1].send_text("新的獎學金")

    assert len(channels) == 2
    assert [client.urls for client in clients] == [[urls[0]], [urls[1]]]
    assert clients[0].messages == []
    assert clients[1].messages == [("Scholarship Agent", "新的獎學金")]
    assert channels[0].channel_id != channels[1].channel_id
    assert "secret" not in channels[0].channel_id


def test_apprise_channel_raises_without_leaking_private_url() -> None:
    private_url = "discord://private-token"

    with pytest.raises(ValueError, match="無效") as invalid_error:
        load_apprise_channels(
            (private_url,),
            "Scholarship Agent",
            lambda: FakeAppriseClient(is_valid=False),
        )
    assert private_url not in str(invalid_error.value)

    channel = AppriseNotificationChannel(
        build_apprise_channel_id(private_url),
        "Scholarship Agent",
        FakeAppriseClient(is_sent=False),
    )
    with pytest.raises(RuntimeError, match="Apprise 通知失敗") as send_error:
        channel.send_text("通知")
    assert private_url not in str(send_error.value)
