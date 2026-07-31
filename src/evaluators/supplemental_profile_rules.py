# -*- coding: utf-8 -*-

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
    return reasons


# 未提供必要學分或紀錄資料時維持 review。
def find_supplemental_unknowns(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if _extract_credit_requirement(text) is not None and profile.credits_earned <= 0:
        reasons.append("公告有學分門檻，但 profile.json 未填累積通過學分。")
    if _contains_any(text, _NO_FAILED_MARKERS) and profile.has_failed_courses is None:
        reasons.append("公告要求無不及格科目，但 profile.json 尚未確認。")
    if _contains_any(text, _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline is None:
        reasons.append("公告要求無記過或重大懲處，但 profile.json 尚未確認。")
    return reasons


# 已確認符合的學分與紀錄可作為輔助證據。
def find_supplemental_matches(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    required = _extract_credit_requirement(text)
    if required is not None and profile.credits_earned >= required:
        reasons.append(f"累積通過學分符合至少 {required} 學分門檻。")
    if _contains_any(text, _NO_FAILED_MARKERS) and profile.has_failed_courses is False:
        reasons.append("無不及格科目，符合公告要求。")
    if _contains_any(text, _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline is False:
        reasons.append("無記過或重大懲處，符合公告要求。")
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


# 判斷文字是否含任一完整條件標記。
def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
