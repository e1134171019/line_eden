# -*- coding: utf-8 -*-

from datetime import date
import re

from src.profiles.student_profile import StudentProfile

_NO_FAILED_MARKERS = (
    "無不及格科目",
    "不得有不及格科目",
    "不得有任何科目不及格",
    "各科均及格",
)
_NO_DISCIPLINE_MARKERS = (
    "未受記過",
    "無記過紀錄",
    "不得有記過",
    "無重大懲處",
    "未受重大懲處",
)
_STUDENT_LOAN_MARKERS = (
    "曾申請就學貸款",
    "申請就學貸款者",
    "背負就學貸款",
    "就學貸款證明文件",
)
_VOLUNTEER_MARKERS = (
    "合作社福單位之志工",
    "合作社福單位擔任志工",
    "合作單位之志工",
    "合作單位擔任志工",
)


# 補足未使用「須／需」引導詞的硬性條件。
def find_supplemental_exclusions(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    required = _extract_credit_requirement(text)
    if required is not None and profile.credits_earned > 0:
        if profile.credits_earned < required:
            reasons.append(
                f"累積通過學分 {profile.credits_earned} 未達 {required} 學分門檻。"
            )
    if _contains_any(text, _NO_FAILED_MARKERS) and profile.has_failed_courses:
        reasons.append("公告要求無不及格科目，但目前紀錄有不及格科目。")
    if _contains_any(text, _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline:
        reasons.append("公告要求無記過或重大懲處，但目前紀錄不符。")
    if _contains_any(text, _STUDENT_LOAN_MARKERS) and profile.has_student_loan is False:
        reasons.append("公告要求曾申請就學貸款，但目前已確認不符合。")
    if (
        _contains_any(text, _VOLUNTEER_MARKERS)
        and profile.has_qualifying_volunteer_service is False
    ):
        reasons.append("公告要求合作單位志工服務，但目前已確認不符合。")
    birth_reason = _birth_date_exclusion(text, profile.birth_date)
    if birth_reason:
        reasons.append(birth_reason)
    return reasons


# 未提供必要學分、紀錄、學貸、志工或生日資料時維持 review。
def find_supplemental_unknowns(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if _extract_credit_requirement(text) is not None and profile.credits_earned <= 0:
        reasons.append("公告有學分門檻，但 profile.json 未填累積通過學分。")
    if _contains_any(text, _NO_FAILED_MARKERS) and profile.has_failed_courses is None:
        reasons.append("公告要求無不及格科目，但 profile.json 尚未確認。")
    if _contains_any(text, _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline is None:
        reasons.append("公告要求無記過或重大懲處，但 profile.json 尚未確認。")
    if _contains_any(text, _STUDENT_LOAN_MARKERS) and profile.has_student_loan is None:
        reasons.append("公告要求曾申請就學貸款，但 profile.json 尚未確認。")
    if (
        _contains_any(text, _VOLUNTEER_MARKERS)
        and profile.has_qualifying_volunteer_service is None
    ):
        reasons.append("公告要求合作單位志工服務，但 profile.json 尚未確認。")
    if _extract_birth_threshold(text) is not None and not _parse_birth_date(profile.birth_date):
        reasons.append("公告有出生日期限制，但 profile.json 未填有效 birth_date。")
    return reasons


# 已確認符合的學分、紀錄、學貸、志工與生日可作為輔助證據。
def find_supplemental_matches(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    required = _extract_credit_requirement(text)
    if required is not None and profile.credits_earned >= required:
        reasons.append(f"累積通過學分符合至少 {required} 學分門檻。")
    if _contains_any(text, _NO_FAILED_MARKERS) and profile.has_failed_courses is False:
        reasons.append("無不及格科目，符合公告要求。")
    if _contains_any(text, _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline is False:
        reasons.append("無記過或重大懲處，符合公告要求。")
    if _contains_any(text, _STUDENT_LOAN_MARKERS) and profile.has_student_loan is True:
        reasons.append("已確認曾申請就學貸款。")
    if (
        _contains_any(text, _VOLUNTEER_MARKERS)
        and profile.has_qualifying_volunteer_service is True
    ):
        reasons.append("已確認具合作單位志工服務。")
    threshold = _extract_birth_threshold(text)
    birth_date = _parse_birth_date(profile.birth_date)
    if threshold and birth_date and birth_date > threshold:
        reasons.append(f"出生日期晚於 {threshold.isoformat()}，符合公告限制。")
    return reasons


# 支援「累計修滿60學分以上」等沒有須／需引導詞的句型。
def _extract_credit_requirement(text: str) -> int | None:
    patterns = (
        r"(?:已修|累計|修滿|取得).{0,10}?(\d{1,3})\s*學分.{0,8}?(?:以上|至少)",
        r"(\d{1,3})\s*學分.{0,8}?(?:以上|至少)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


# 擷取「民國85年1月1日後出生」等民國日期門檻。
def _extract_birth_threshold(text: str) -> date | None:
    match = re.search(
        r"民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:後|以後)出生",
        text,
    )
    if not match:
        return None
    year, month, day = (int(value) for value in match.groups())
    try:
        return date(year + 1911, month, day)
    except ValueError:
        return None


# profile 使用 ISO 日期；空白或格式錯誤都視為尚未提供。
def _parse_birth_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# 已提供生日且未通過「某日後出生」門檻時回傳硬性不符。
def _birth_date_exclusion(text: str, value: str) -> str | None:
    threshold = _extract_birth_threshold(text)
    birth_date = _parse_birth_date(value)
    if threshold and birth_date and birth_date <= threshold:
        return f"公告限 {threshold.isoformat()} 後出生，與目前生日不符。"
    return None


# 判斷文字是否含任一完整條件標記。
def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
