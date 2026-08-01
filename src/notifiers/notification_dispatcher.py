# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Callable, Protocol


class NotificationChannel(Protocol):
    """單一通知目的地必須提供的介面。"""

    @property
    def channel_id(self) -> str:
        """回傳不含憑證的穩定管道識別碼。"""
        ...

    def send_text(self, text: str) -> None:
        """傳送純文字，失敗時必須拋出例外。"""
        ...


class NotificationDispatcher(Protocol):
    """服務層使用的多管道通知介面。"""

    def channel_ids(self) -> tuple[str, ...]:
        """回傳目前啟用的管道識別碼。"""
        ...

    def send_text(self, channel_id: str, text: str) -> None:
        """只傳送至指定管道，失敗時必須拋出例外。"""
        ...


@dataclass(frozen=True)
class CallableNotificationChannel:
    """把既有 callable 包裝成具名通知管道。"""

    channel_id: str
    sender: Callable[[str], None]

    def send_text(self, text: str) -> None:
        self.sender(text)


@dataclass(frozen=True)
class NotificationFanout:
    """依 channel_id 將訊息路由到單一通知管道。"""

    channels: tuple[NotificationChannel, ...]

    def __post_init__(self) -> None:
        validate_channel_ids(self.channels)

    def channel_ids(self) -> tuple[str, ...]:
        return tuple(channel.channel_id for channel in self.channels)

    def send_text(self, channel_id: str, text: str) -> None:
        channel = select_notification_channel(self.channels, channel_id)
        channel.send_text(text)


def validate_channel_ids(channels: tuple[NotificationChannel, ...]) -> None:
    """純函式：拒絕空白或重複的通知管道識別碼。"""
    channel_ids = [channel.channel_id for channel in channels]
    if any(
        not channel_id.strip() or channel_id != channel_id.strip()
        for channel_id in channel_ids
    ):
        raise ValueError("通知管道 channel_id 不得空白或包含首尾空白")
    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("通知管道 channel_id 不得重複")


def select_notification_channel(
    channels: tuple[NotificationChannel, ...],
    channel_id: str,
) -> NotificationChannel:
    """純函式：依識別碼選出單一通知管道。"""
    for channel in channels:
        if channel.channel_id == channel_id:
            return channel
    raise KeyError(f"找不到通知管道：{channel_id}")
