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
    application_status: str = "",
) -> SimpleNamespace:
    item = SimpleNamespace(
        eligibility_status=status,
        published_date="2026-07-28",
        title=title,
        eligibility_reason="符合目前學生背景。",
        source_url="https://example.test/notice",
        detail_url="https://example.test/detail",
        notice_kind=notice_kind,
        category=category,
        application_status=application_status,
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


def test_report_lists_current_eligible_and_review_items() -> None:
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
            "來源網站：設定 7，成功產生資料 7，空結果 0，部分完成 0，失敗 0",
            "龍華科技大學：完整；頁面 5/5",
        ],
    )

    assert "本次稽核公告：3" in message
    assert "申請型公告：2" in message
    assert "公告類別：獎學金 2／助學金 1" in message
    assert "申請狀態：開放 2" in message
    assert "個人資格（未截止與期限未知）：符合 1／待確認 1／硬性不符 0" in message
    assert "非申請公告未列入個人資格：1" in message
    assert "來源網站：設定 7" in message
    assert "龍華科技大學：完整" in message
    assert "符合資格的獎學金" in message
    assert "資格待確認公告：" in message
    assert "待確認公告" in message
    assert "不符合公告" not in message


def test_expired_notice_is_not_counted_as_personal_ineligibility() -> None:
    result = _result(
        records=[
            _record(
                "ineligible",
                "過期獎學金",
                text="申請截止日期為2025/09/30。",
            )
        ],
        ineligible_count=1,
    )

    message = build_report_message(result)

    assert "個人資格（未截止與期限未知）：符合 0／待確認 0／硬性不符 0" in message
    assert "已截止未列為個人資格不符：1" in message
    assert "過期獎學金" not in message


def test_report_lists_review_when_no_eligible_items() -> None:
    result = _result(
        records=[_record("review", "待確認公告")],
        review_count=1,
        gemini_calls=1,
    )

    message = build_report_message(result)

    assert "本次稽核公告：1" in message
    assert "資格待確認公告：" in message
    assert "待確認公告" in message
    assert "目前沒有符合或待確認且仍可申請的公告。" not in message
    assert "LINE Messaging API 測試成功" not in message


def test_actionable_items_appear_before_compact_tun_status() -> None:
    result = _result(
        records=[
            _record("eligible", "優先顯示的符合公告"),
            _record("review", "優先顯示的待確認公告"),
        ],
        eligible_count=1,
        review_count=1,
    )
    source_lines = [
        "來源網站：設定 7，成功產生資料 7，空結果 0，部分完成 0，失敗 0"
    ]
    source_lines.extend(
        f"TUN方案 program-{index}：candidate_found；候選 1；入口 https://example.test/{index}"
        for index in range(35)
    )
    source_lines.extend(
        f"TUN方案 pending-{index}：pending_source；候選 0；入口 由核心來源涵蓋"
        for index in range(3)
    )

    message = build_report_message(result, source_lines)

    assert len(message) <= 4800
    assert "優先顯示的符合公告" in message
    assert "優先顯示的待確認公告" in message
    assert "TUN方案共 38：candidate_found 35／pending_source 3" in message
    assert message.index("優先顯示的符合公告") < message.index("TUN方案共 38")
    assert "TUN方案 program-20" not in message


def test_report_lists_structured_divergence_and_error_details() -> None:
    changed = _record("review", "Structured 判斷不同的公告")
    changed.structured_shadow = SimpleNamespace(
        changed=True,
        legacy_status="review",
        structured_status="ineligible",
        structured_reason="公告明確限定研究生。",
    )
    changed.shadow_status = "compared"
    changed.structured_gemini_diagnostic = None

    failed = _record("review", "Gemini 暫時失敗公告")
    failed.structured_shadow = None
    failed.shadow_status = "text_error"
    failed.structured_gemini_diagnostic = SimpleNamespace(
        message="ServerError: 503 temporarily unavailable"
    )
    result = _result(
        records=[changed, failed],
        structured_evaluated_count=1,
        structured_changed_count=1,
        structured_error_count=1,
    )

    message = build_report_message(result)

    assert "Structured 分歧明細：" in message
    assert "review→ineligible" in message
    assert "公告明確限定研究生" in message
    assert "Structured 抽取錯誤：" in message
    assert "503 temporarily unavailable" in message
