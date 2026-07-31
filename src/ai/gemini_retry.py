# -*- coding: utf-8 -*-

from collections.abc import Callable
import re
import time
from typing import TypeVar

T = TypeVar("T")
_TRANSIENT_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_MARKERS = (
    "resource_exhausted",
    "unavailable",
    "deadline_exceeded",
    "internal",
    "timeout",
    "timed out",
    "connection reset",
    "temporarily unavailable",
    "server error",
)


# 對可恢復的 Gemini API 錯誤執行有限次指數退避重試。
def run_with_retry(
    operation: Callable[[], T],
    max_attempts: int,
    base_seconds: int,
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    if max_attempts < 1:
        raise ValueError("Gemini 最大嘗試次數必須大於 0")
    for attempt in range(max_attempts):
        try:
            return operation()
        except Exception as error:
            if attempt + 1 >= max_attempts or not is_transient_error(error):
                raise
            sleeper(base_seconds * (2**attempt))
    raise RuntimeError("Gemini 重試流程未回傳結果")


# 僅將配額、逾時、連線與服務端錯誤視為可重試。
def is_transient_error(error: Exception) -> bool:
    text = _error_text(error)
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return True
    return any(
        int(code) in _TRANSIENT_CODES
        for code in re.findall(r"(?<!\d)(429|500|502|503|504)(?!\d)", text)
    )


# 合併例外類型、訊息與 SDK 狀態欄位，供穩定判斷。
def _error_text(error: Exception) -> str:
    values = [type(error).__name__, str(error)]
    for name in ("status_code", "code"):
        value = getattr(error, name, "")
        if callable(value):
            try:
                value = value()
            except TypeError:
                value = ""
        values.append(str(value))
    return " ".join(values).lower()
