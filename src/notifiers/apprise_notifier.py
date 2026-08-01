# -*- coding: utf-8 -*-

from dataclasses import dataclass
import hashlib
from typing import Callable, Protocol

import apprise


class AppriseClient(Protocol):
    """隔離第三方 Apprise 物件的最小介面。"""

    def add(self, servers: str) -> bool:
        """加入單一通知 URL。"""
        ...

    def notify(self, *, body: str, title: str) -> bool | None:
        """送出文字通知並回傳整體成功狀態。"""
        ...


class AppriseClientFactory(Protocol):
    """建立 Apprise client 的可替換工廠介面。"""

    def __call__(self) -> AppriseClient:
        """建立尚未載入通知 URL 的 client。"""
        ...


@dataclass(frozen=True)
class AppriseNotificationChannel:
    """單一 Apprise URL 的通知 adapter。"""

    channel_id: str
    title: str
    client: AppriseClient

    def send_text(self, text: str) -> None:
        is_sent = self.client.notify(body=text, title=self.title)
        if is_sent is not True:
            raise RuntimeError("Apprise 通知失敗")


def build_apprise_channel_id(notification_url: str) -> str:
    """純函式：由 URL 建立不洩漏憑證的穩定管道識別碼。"""
    digest = hashlib.sha256(notification_url.strip().encode("utf-8")).hexdigest()
    return f"apprise-{digest[:16]}"


def load_apprise_channels(
    notification_urls: tuple[str, ...],
    title: str,
    client_factory: AppriseClientFactory | Callable[[], AppriseClient] = apprise.Apprise,
) -> tuple[AppriseNotificationChannel, ...]:
    """載入並驗證每個 Apprise URL，各自建立可獨立重試的管道。"""
    return tuple(
        load_apprise_channel(notification_url, title, client_factory)
        for notification_url in notification_urls
    )


def load_apprise_channel(
    notification_url: str,
    title: str,
    client_factory: AppriseClientFactory | Callable[[], AppriseClient],
) -> AppriseNotificationChannel:
    """載入單一 Apprise URL；錯誤訊息不得包含私密 URL。"""
    client = client_factory()
    if client.add(notification_url) is not True:
        raise ValueError("APPRISE_URLS 含有無效的通知 URL")
    return AppriseNotificationChannel(
        channel_id=build_apprise_channel_id(notification_url),
        title=title,
        client=client,
    )
