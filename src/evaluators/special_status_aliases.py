# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

STATUS_ALIASES = {
    "低收入戶": ("低收入戶", "低收入學生", "低收學生", "低收"),
    "中低收入戶": ("中低收入戶", "中低收入學生", "中低收學生", "中低收"),
    "清寒": ("清寒", "家庭清寒", "家境清寒"),
    "經濟弱勢": ("經濟弱勢", "經濟不利", "家境困難", "家庭經濟困難"),
    "特殊境遇家庭": ("特殊境遇家庭", "特殊境遇"),
    "遭逢變故": ("遭逢變故", "突遭變故", "家庭變故"),
    "重大變故": ("重大變故", "家庭重大變故"),
    "重大疾病": ("重大疾病", "罹患重病"),
    "身心障礙": ("身心障礙", "身障"),
    "原住民": ("原住民", "原住民族"),
    "失業勞工子女": ("失業勞工子女",),
    "顱顏患者": ("顱顏患者", "顱顏病友", "顱顏家庭子女"),
    "癌友家庭子女": ("癌友家庭子女", "癌症家庭子女", "癌症病友子女"),
    "新住民子女": ("新住民子女", "新移民子女"),
    "警察子女": ("警察子女", "警眷子女"),
    "軍警消子女": ("軍警消子女", "軍人子女", "消防人員子女"),
}
PREFERENCE_WORDS = ("優先", "加分", "不限", "非必要")
REQUIREMENT_WORDS = (
    "限",
    "僅限",
    "申請對象",
    "申請資格",
    "資格條件",
    "救助對象",
    "補助對象",
    "獎助對象",
    "適用對象",
    "對象為",
    "須為",
    "需為",
    "須具備",
    "需具備",
    "申請人須",
    "申請者須",
    "具有",
    "具備",
)
ANY_OF_WORDS = ("或", "任一", "擇一", "其中一項", "下列之一", "、")


# 補足家庭與法定身分的常見同義詞及 any-of 排除判斷。
def find_alias_exclusions(
    title: str,
    text: str,
    profile: StudentProfile,
) -> list[str]:
    owned = set(profile.special_statuses)
    title_reason = _title_exclusion(title, owned)
    if title_reason:
        return [title_reason]
    for sentence in re.split(r"[。；;\n]", text):
        normalized = " ".join(sentence.split())
        if not normalized or _contains_preference(normalized):
            continue
        statuses = _mentioned_statuses(normalized)
        if not statuses or not _contains_requirement(normalized):
            continue
        if len(statuses) > 1 and any(word in normalized for word in ANY_OF_WORDS):
            if not any(_owns_status(owned, status) for status in statuses):
                return [f"須具備以下任一身分：{'、'.join(statuses)}。"]
            continue
        for status in statuses:
            if not _owns_status(owned, status):
                return [f"公告限定「{status}」身分。"]
    return []


# 標題直接以特定身分命名且非優先條件時視為必要資格。
def _title_exclusion(title: str, owned: set[str]) -> str | None:
    if _contains_preference(title):
        return None
    for canonical, aliases in STATUS_ALIASES.items():
        if any(alias in title for alias in aliases) and not _owns_status(owned, canonical):
            return f"公告限定「{canonical}」身分。"
    return None


# 取得單一句子實際提及的 canonical 身分，並保持規則順序。
def _mentioned_statuses(sentence: str) -> tuple[str, ...]:
    return tuple(
        canonical
        for canonical, aliases in STATUS_ALIASES.items()
        if any(alias in sentence for alias in aliases)
    )


# 判斷 profile 是否具有 canonical 或任一常見同義身分。
def _owns_status(owned: set[str], canonical: str) -> bool:
    aliases = STATUS_ALIASES.get(canonical, (canonical,))
    return canonical in owned or any(alias in owned for alias in aliases)


# 判斷句子是否將身分列為申請／救助對象或必要資格。
def _contains_requirement(text: str) -> bool:
    return any(word in text for word in REQUIREMENT_WORDS)


# 判斷文字是否只是優先或非必要條件。
def _contains_preference(text: str) -> bool:
    return any(word in text for word in PREFERENCE_WORDS)
