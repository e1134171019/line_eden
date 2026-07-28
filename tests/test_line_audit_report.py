# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.automation.line_audit_report import build_report_message


def _record(status: str, title: str) -> SimpleNamespace:
    item = SimpleNamespace(
        eligibility_status=status,
        published_date="2026-07-28",
        title=title,
        eligibility_reason="符合目前學生背景。",
        source_url="https://example.test/notice",
    )
    return SimpleNamespace(item=item)


def _result(
    records: list[SimpleNamespace],
    *,
    eligible: int,
    review: int,
    ineligible: int,
    gemini_calls: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        records=records,
        eligible_count=eligible,
        review_count=review,
        ineligible_count=ineligible,
        gemini_calls=gemini_calls,
        gemini_cache_hits=0,
        structured_evaluated_count=0,
        structured_changed_count=0,
        structured_deferred_count=0,
        structured_error_count=0,
    )


def test_report_lists_only_eligible_items() -> None:
    result = _result(
        [
            _record("eligible", "符合資格的獎學金"),
            _record("review", "待確認公告"),
            _record("ineligible", "不符合公告"),
        ],
        eligible=1,
        review=1,
        ineligible=1,
    )

    message = build_report_message(
        result,
        [
            "龍華科技大學：讀取 80 筆，保留 80 筆",
            "教育部圓夢助學網－民間團體：讀取 10 筆，保留 8 筆，跨站重複 2 筆",
        ],
    )

    assert "官方來源：5 個" in message
    assert "龍華科技大學：讀取 80 筆" in message
    assert "跨站重複 2 筆" in message
    assert "明確適合：1" in message
    assert "資格待確認：1（不推播）" in message
    assert "符合資格的獎學金" in message
    assert "待確認公告" not in message
    assert "不符合公告" not in message


def test_report_explains_when_no_eligible_items() -> None:
    result = _result(
        [_record("review", "待確認公告")],
        eligible=0,
        review=1,
        ineligible=0,
        gemini_calls=1,
    )

    message = build_report_message(result)

    assert "稽核公告：1" in message
    assert "目前沒有明確符合你背景的公告。" in message
    assert "LINE Messaging API 測試成功" not in message
