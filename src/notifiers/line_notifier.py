# -*- coding: utf-8 -*-

import httpx


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
