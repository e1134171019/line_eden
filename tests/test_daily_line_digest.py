# -*- coding: utf-8 -*-

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.automation import daily_line_digest
from src.services.scholarship_service import ServiceResult


class FakeCollector:
    def source_summary_lines(self) -> list[str]:
        return [
            "龍華科技大學：讀取 10 筆，保留 10 筆",
            "教育部圓夢助學網－民間團體：讀取 5 筆，保留 4 筆，跨站重複 1 筆",
        ]


class FakeService:
    def __init__(self, result: ServiceResult | None = None, error: Exception | None = None) -> None:
        self.collector = FakeCollector()
        self.result = result
        self.error = error
        self.calls: list[bool] = []

    def run(self, dry_run: bool) -> ServiceResult:
        self.calls.append(dry_run)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _result(notified_count: int = 0) -> ServiceResult:
    collected = [SimpleNamespace(), SimpleNamespace()]
    return ServiceResult(
        collected=collected,
        pending_items=[],
        notified_count=notified_count,
        baseline_count=0,
        message="沒有適合目前背景的待通知公告。",
        eligible_count=0,
        review_count=3,
        ineligible_count=7,
        gemini_calls=0,
        gemini_cache_hits=0,
        gemini_input_tokens=0,
        gemini_output_tokens=0,
        current_eligible_count=1,
        current_review_count=1,
        current_ineligible_count=0,
        current_unevaluated_count=0,
    )


def test_daily_message_is_sent_even_without_eligible_items() -> None:
    checked_at = datetime(2026, 7, 28, 7, 30, tzinfo=ZoneInfo("Asia/Taipei"))

    message = daily_line_digest.build_daily_message(
        _result(),
        ["龍華科技大學：讀取 10 筆，保留 10 筆"],
        checked_at,
    )

    assert "獎學金每日檢查完成" in message
    assert "時間：2026-07-28 07:30" in message
    assert "本次符合並通知：0" in message
    assert "本輪來源實際判定：符合 1／待確認 1／不符合 0／未評估 0" in message
    assert "通知前資料庫待處理：符合 0／待確認 3／不符合 7" in message
    assert "今天沒有新的明確符合公告。" in message
    assert "龍華科技大學：讀取 10 筆，保留 10 筆" in message


def test_daily_main_sends_completion_summary(monkeypatch: Any) -> None:
    service = FakeService(_result())
    messages: list[str] = []
    monkeypatch.setattr(daily_line_digest, "validate_settings", lambda: None)
    monkeypatch.setattr(daily_line_digest, "validate_gemini_settings", lambda: None)
    monkeypatch.setattr(daily_line_digest, "build_service", lambda **_: service)
    monkeypatch.setattr(daily_line_digest, "_send", messages.append)

    daily_line_digest.main()

    assert service.calls == [False]
    assert len(messages) == 1
    assert "獎學金每日檢查完成" in messages[0]
    assert "教育部圓夢助學網－民間團體" in messages[0]


def test_daily_main_sends_failure_alert_and_reraises(monkeypatch: Any) -> None:
    service = FakeService(error=RuntimeError("five sources unavailable"))
    messages: list[str] = []
    monkeypatch.setattr(daily_line_digest, "validate_settings", lambda: None)
    monkeypatch.setattr(daily_line_digest, "validate_gemini_settings", lambda: None)
    monkeypatch.setattr(daily_line_digest, "build_service", lambda **_: service)
    monkeypatch.setattr(daily_line_digest, "_send", messages.append)

    with pytest.raises(RuntimeError, match="five sources unavailable"):
        daily_line_digest.main()

    assert len(messages) == 1
    assert "獎學金每日檢查失敗" in messages[0]
    assert "five sources unavailable" in messages[0]
