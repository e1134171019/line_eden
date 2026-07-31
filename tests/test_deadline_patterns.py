# -*- coding: utf-8 -*-

from datetime import date

from src.evaluators.runtime_safety import EXPIRED, classify_application_period, extract_application_deadline


# 動作位於日期後方的上網登錄句型必須可解析。
def test_extracts_online_registration_before_date() -> None:
    deadline = extract_application_deadline(
        "請將資料備妥，於9/20前上網登錄資料並完成送件。",
        "2024-09-09",
    )

    assert deadline == date(2024, 9, 20)


# 收件或系統截止句型必須可解析民國日期。
def test_extracts_system_deadline() -> None:
    deadline = extract_application_deadline(
        "線上系統收件截止日期為115/09/20。",
        "2026-08-01",
    )

    assert deadline == date(2026, 9, 20)


# 即日起至指定日期止應擷取結束日期。
def test_extracts_from_now_until_date() -> None:
    deadline = extract_application_deadline(
        "申請期間即日起至115/10/31止。",
        "2026-08-01",
    )

    assert deadline == date(2026, 10, 31)


# 日期在前且以郵戳為憑的寄送規則必須可解析。
def test_extracts_postmark_deadline() -> None:
    deadline = extract_application_deadline(
        "申請資料請自行寄送，9/30前郵戳為憑。",
        "2024-08-28",
    )

    assert deadline == date(2024, 9, 30)


# 無年份日期使用公告發布年份，歷史公告應直接判定已截止。
def test_old_notice_uses_published_year_and_is_expired() -> None:
    period = classify_application_period(
        "請於9/20前上網登錄資料。",
        "2024-09-09",
        today=date(2026, 7, 31),
    )

    assert period.deadline == date(2024, 9, 20)
    assert period.status == EXPIRED
