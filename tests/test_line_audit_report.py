# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.automation.line_audit_report import build_report_message


def _record(
    status: str,
    title: str,
    *,
    notice_kind: str = "application",
    application_status: str = "open",
    source_url: str = "https://example.test/notice",
    detail_url: str = "https://example.test/detail",
    text: str = "請於2026/09/30前完成申請。",
) -> SimpleNamespace:
    item = SimpleNamespace(
        eligibility_status=status,
        hard_eligibility_status=status,
        title=title,
        source_url=source_url,
        detail_url=detail_url,
        notice_kind=notice_kind,
        application_status=application_status,
    )
    fetch_result = SimpleNamespace(eligibility_text=lambda: text)
    return SimpleNamespace(item=item, fetch_result=fetch_result)


def _result(records: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(records=records)


def test_report_only_lists_eligible_titles_and_links() -> None:
    result = _result(
        [
            _record("eligible", "符合資格公告一"),
            _record(
                "eligible",
                "符合資格公告二",
                source_url="https://example.test/notice-2",
                detail_url="https://example.test/detail-2",
                application_status="upcoming",
            ),
            _record("review", "待確認公告"),
            _record("ineligible", "不符合公告"),
            _record("eligible", "非申請公告", notice_kind="result"),
        ]
    )

    message = build_report_message(
        result,
        ["來源網站：成功 44，失敗 0", "TUN方案 a：matched"],
    )

    assert message == (
        "【符合資格獎學金】\n"
        "1. 符合資格公告一\n"
        "https://example.test/detail\n"
        "2. 符合資格公告二\n"
        "https://example.test/detail-2"
    )
    assert "來源" not in message
    assert "待確認公告" not in message
    assert "不符合公告" not in message
    assert "符合原因" not in message
    assert "正文證據" not in message
    assert "Structured" not in message


def test_report_excludes_expired_and_stale_notices() -> None:
    result = _result(
        [
            _record("eligible", "已截止公告", application_status="expired"),
            _record("eligible", "歷史公告", application_status="stale_unknown"),
        ]
    )

    message = build_report_message(result)

    assert message == "目前沒有符合資格且仍可申請的獎學金。"


def test_report_uses_detail_url_and_deduplicates_same_link() -> None:
    result = _result(
        [
            _record("eligible", "第一筆"),
            _record("eligible", "重複連結第二筆"),
        ]
    )

    message = build_report_message(result)

    assert message.count("https://example.test/detail") == 1
    assert "第一筆" in message
    assert "重複連結第二筆" not in message
