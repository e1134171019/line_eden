# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

_RESIDENCE_MISMATCH = re.compile(r"公告限設籍於 (.+)，與目前戶籍地不符。")


# 移除行政區前方介系詞造成的假性戶籍不符。
def filter_false_residence_exclusions(
    reasons: list[str],
    profile: StudentProfile,
) -> list[str]:
    normalized_residence = _normalize_region(profile.residence)
    filtered: list[str] = []
    for reason in reasons:
        match = _RESIDENCE_MISMATCH.fullmatch(reason)
        if match is None:
            filtered.append(reason)
            continue
        required = _normalize_region(match.group(1).lstrip("於在 "))
        if required and required in normalized_residence:
            continue
        filtered.append(reason)
    return filtered


# 統一臺／台與空白後再比較行政區。
def _normalize_region(value: str) -> str:
    return value.replace("臺", "台").replace(" ", "")
