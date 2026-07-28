# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.automation.line_audit_report import build_report_message


# 建立可供報表統計的簡化稽核紀錄。
def _record(
    status: str,
    title: str,
    *,
    notice_kind: str = "application",
    category: str = "scholarship",
    text: str = "請於2026/09/30前完成申請。",
) -> SimpleNamespace:
    item = SimpleNamespace(
        eligibility_status=status,
        published_date="2026-07-28",
        title=title,
        eligibility_reason="符合目前學生背景。",
        source_url="https://example.test/notice",
        notice_kind=notice_kind,
        category=category,
    )
    fetch_result = SimpleNamespace(eligibility_text=lambda: text)
    return SimpleNamespace(item=item, fetch_result=fetch_result)


# 建立簡化稽核結果。
def _result(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "records": [],
        "eligible_count": 0,
        "review_count": 0,
        "ineligible_count": 0,
        "gemini_calls": 0,
        "gemini_cache_hits": 0,
        "structured_evaluated_count": 0,
        "structured_changed_count": 0,
        "structured_deferred_count": 0,
        "structured_error_count": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_report_lists_only_eligible_items() -> None:
    result = _result(
        records=[
            _record("eligible", "符合資格的獎學金"),
            _record("review", "待確認公告", category="student_aid"),
            _record("ineligible", "不符合公告", notice_kind="result"),
        ],
        eligible_count=1,
        review_count=1,
        ineligible_count=1,
    )

    message = build_report_message(
        result,
        [
            "來源健康：降級；設定 5，有資料 2，空結果 2，失敗 1",
            "龍華科技大學：讀取 80 筆，保留 80 筆",
        ],
    )

    assert "原始公告：3" in message
    assert "申請型公告：2" in message
    assert "公告類別：獎學金 2／助學金 1" in message
    assert "申請狀態：開放 2" in message
    assert "來源健康：降級" in message
    assert "龍華科技大學：讀取 80 筆" in message
    assert "明確適合：1" in message
    assert "資格待確認：1（不推播）" in message
    assert "符合資格的獎學金" in message
    assert "待確認公告" not in message
    assert "不符合公告" not in message


def test_report_explains_when_no_eligible_items() -> None:
    result = _result(
        records=[_record("review", "待確認公告")],
        review_count=1,
        gemini_calls=1,
    )

    message = build_report_message(result)

    assert "原始公告：1" in message
    assert "目前沒有明確符合你背景且仍可申請的公告。" in message
    assert "LINE Messaging API 測試成功" not in message
