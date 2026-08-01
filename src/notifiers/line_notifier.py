# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Protocol

import httpx


class LineSender(Protocol):
    """LINE transport 的完整可替換呼叫介面。"""

    def __call__(
        self,
        *,
        api_url: str,
        channel_access_token: str,
        user_id: str,
        text: str,
        timeout_seconds: float,
    ) -> None:
        """傳送單一 LINE 純文字訊息。"""
        ...


# 建立 LINE Messaging API 的授權標頭。
def build_headers(channel_access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {channel_access_token}",
        "Content-Type": "application/json",
    }


# 建立 LINE 文字推播所需的 JSON 資料。
def build_payload(user_id: str, text: str) -> dict[str, object]:
    return {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }


# 將一則文字訊息推播至指定 LINE 使用者。
def send_text_message(
    api_url: str,
    channel_access_token: str,
    user_id: str,
    text: str,
    timeout_seconds: float,
) -> None:
    response = httpx.post(
        api_url,
        headers=build_headers(channel_access_token),
        json=build_payload(user_id, text),
        timeout=timeout_seconds,
    )
    response.raise_for_status()


@dataclass(frozen=True)
class LineNotificationChannel:
    """LINE Messaging API 的具名通知管道。"""

    channel_id: str
    api_url: str
    channel_access_token: str
    user_id: str
    timeout_seconds: float
    sender: LineSender = send_text_message

    def send_text(self, text: str) -> None:
        self.sender(
            api_url=self.api_url,
            channel_access_token=self.channel_access_token,
            user_id=self.user_id,
            text=text,
            timeout_seconds=self.timeout_seconds,
        )
