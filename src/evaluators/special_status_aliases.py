# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

STATUS_ALIASES = {
    "低收入戶": ("低收入戶", "低收入學生", "低收學生", "低收"),
    "中低收入戶": ("中低收入戶", "中低收入學生", "中低收學生", "中低收"),
    "失業勞工子女": ("失業勞工子女",),
    "顱顏患者": ("顱顏患者", "顱顏病友", "顱顏家庭子女"),
    "癌友家庭子女": ("癌友家庭子女", "癌症家庭子女", "癌症病友子女"),
    "新住民子女": ("新住民子女", "新移民子女"),
    "警察子女": ("警察子女", "警眷子女"),
    "軍警消子女": ("軍警消子女", "軍人子女", "消防人員子女"),
}
PREFERENCE_WORDS = ("優先", "加分", "不限", "非必要")
REQUIREMENT_WORDS = r"(?:限|僅限|申請對象|申請資格|資格條件|須為|需為|具有|具備)"


# 補足家庭與法定身分的常見同義詞排除判斷。
def find_alias_exclusions(
    title: str,
    text: str,
    profile: StudentProfile,
) -> list[str]:
    owned = set(profile.special_statuses)
    for canonical, aliases in STATUS_ALIASES.items():
        if canonical in owned or any(alias in owned for alias in aliases):
            continue
        if _title_requires_status(title, aliases) or _text_requires_status(text, aliases):
            return [f"公告限定「{canonical}」身分。"]
    return []


# 標題直接以特定身分命名且非優先條件時視為必要資格。
def _title_requires_status(title: str, aliases: tuple[str, ...]) -> bool:
    return any(alias in title for alias in aliases) and not _contains_preference(title)


# 正文只有在限制語境中出現同義詞時才視為必要資格。
def _text_requires_status(text: str, aliases: tuple[str, ...]) -> bool:
    pattern = "|".join(re.escape(alias) for alias in aliases)
    for sentence in re.split(r"[。；;\n]", text):
        if _contains_preference(sentence):
            continue
        if re.search(rf"{REQUIREMENT_WORDS}.{{0,20}}(?:{pattern})", sentence):
            return True
    return False


# 判斷文字是否只是優先或非必要條件。
def _contains_preference(text: str) -> bool:
    return any(word in text for word in PREFERENCE_WORDS)
