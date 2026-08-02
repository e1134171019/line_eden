# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

STATUS_ALIASES = {
    "低收入戶": ("低收入戶", "低收入學生", "低收學生", "低收"),
    "中低收入戶": ("中低收入戶", "中低收入學生", "中低收學生", "中低收"),
    "清寒": ("清寒", "家庭清寒", "家境清寒", "清寒邊緣戶", "家境清寒之邊緣戶"),
    "經濟弱勢": (
        "經濟弱勢",
        "經濟不利",
        "家境困難",
        "家庭經濟困難",
        "家庭經濟困境",
        "經濟困境",
        "經濟拮据",
        "收入不足維持家庭生活",
        "收入不足以維持家庭生活",
    ),
    "特殊境遇家庭": ("特殊境遇家庭", "特殊境遇"),
    "遭逢變故": ("遭逢變故", "突遭變故", "家庭變故", "家庭突遭變故"),
    "重大變故": ("重大變故", "家庭重大變故"),
    "重大疾病": ("重大疾病", "罹患重病"),
    "身心障礙": ("身心障礙", "身障", "肢體障礙", "肢障"),
    "原住民": ("原住民", "原住民族"),
    "失業勞工子女": ("失業勞工子女",),
    "燒燙傷傷友": ("燒燙傷傷友", "燒燙傷者", "燒傷傷友", "燒傷者"),
    "陽光傷友子女": ("陽光傷友子女", "傷友子女"),
    "顱顏患者": ("顱顏患者", "顱顏病友", "顱顏家庭子女"),
    "心臟病童": (
        "心臟病童",
        "先天性心臟病童",
        "接受心臟導管治療",
        "接受心臟外科手術治療",
    ),
    "癌友家庭子女": ("癌友家庭子女", "癌症家庭子女", "癌症病友子女"),
    "新住民子女": ("新住民子女", "新移民子女"),
    "警察子女": ("警察子女", "警眷子女"),
    "軍警消子女": ("軍警消子女", "軍人子女", "消防人員子女"),
    "熱河省籍": (
        "熱河省籍",
        "祖籍熱河省",
        "祖籍符合國民政府熱河省",
        "國民政府熱河省建置",
    ),
    "海外來台學生": (
        "海外來台就讀",
        "海外來台學生",
        "來台就讀國內公私立大學",
    ),
}
PREFERENCE_WORDS = (
    "優先",
    "優先考量",
    "優先錄取",
    "優先審核",
    "同分優先",
    "加分",
    "酌予優先",
    "不限",
    "非必要",
)
AMBIGUOUS_WORDS = (
    "以弱勢為原則",
    "以經濟弱勢為原則",
    "主要協助弱勢",
    "主要提供弱勢",
    "特別考量弱勢",
)
REQUIREMENT_WORDS = (
    "限",
    "僅限",
    "申請對象",
    "申請資格",
    "申請條件",
    "共同申請條件",
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
    "至少符合",
    "符合下列",
    "符合以下",
    "申請人須",
    "申請者須",
    "具有",
    "具備",
)
ANY_OF_WORDS = (
    "或",
    "任一",
    "擇一",
    "其中一項",
    "其中之一",
    "下列之一",
    "各款情形之一",
)
_GROUP_HEADER_WORDS = (
    "申請資格",
    "申請條件",
    "共同申請條件",
    "符合下列",
    "符合以下",
)
_GROUP_LOOKAHEAD = 8


# 對已確認身分的 profile 檢查必要特殊身分；優先條件不造成排除。
def find_alias_exclusions(
    title: str,
    text: str,
    profile: StudentProfile,
) -> list[str]:
    if not profile.special_statuses_confirmed:
        return []
    owned = set(profile.special_statuses)
    title_reason = _title_exclusion(title, owned)
    if title_reason:
        return [title_reason]
    group_reason = _group_exclusion(text, owned)
    if group_reason:
        return [group_reason]
    for sentence in _sentences(text):
        if _contains_preference(sentence) or _contains_ambiguous(sentence):
            continue
        statuses = _mentioned_statuses(sentence)
        if not statuses or not _contains_requirement(sentence):
            continue
        missing = tuple(status for status in statuses if not _owns_status(owned, status))
        if not missing:
            continue
        if len(statuses) > 1 and _contains_any_of(sentence):
            if len(missing) == len(statuses):
                return [f"須具備以下任一身分：{'、'.join(statuses)}。"]
            continue
        return [f"公告限定「{missing[0]}」身分。"]
    return []


# 身分資料未確認或資格語意模糊時維持 review，不猜測符合或不符合。
def find_alias_unknowns(text: str, profile: StudentProfile) -> list[str]:
    owned = set(profile.special_statuses)
    groups = _required_status_groups(text)
    if groups and not profile.special_statuses_confirmed:
        return ["公告要求經濟或特殊身分，但 profile.json 尚未確認相關身分。"]
    for any_of, statuses in groups:
        satisfied = (
            any(_owns_status(owned, status) for status in statuses)
            if any_of
            else all(_owns_status(owned, status) for status in statuses)
        )
        if satisfied:
            continue
        if not profile.special_statuses_confirmed:
            return ["公告要求經濟或特殊身分，但 profile.json 尚未確認相關身分。"]
    for sentence in _sentences(text):
        statuses = _mentioned_statuses(sentence)
        if not statuses or _contains_preference(sentence):
            continue
        if all(_owns_status(owned, status) for status in statuses):
            continue
        if _contains_ambiguous(sentence):
            return ["公告對經濟或特殊身分的要求語意不明，需人工確認。"]
        if _contains_requirement(sentence) and not profile.special_statuses_confirmed:
            return ["公告要求經濟或特殊身分，但 profile.json 尚未確認相關身分。"]
    return []


# 解析跨行資格條列，回傳是否 any-of 與條列提及的身分。
def _required_status_groups(text: str) -> tuple[tuple[bool, tuple[str, ...]], ...]:
    sentences = _sentences(text)
    groups: list[tuple[bool, tuple[str, ...]]] = []
    for index, sentence in enumerate(sentences):
        if _mentioned_statuses(sentence) or not _is_group_header(sentence):
            continue
        statuses: list[str] = []
        for following in sentences[index + 1 : index + 1 + _GROUP_LOOKAHEAD]:
            if _is_group_header(following):
                break
            mentioned = _mentioned_statuses(following)
            if mentioned:
                statuses.extend(item for item in mentioned if item not in statuses)
                continue
            if statuses:
                break
        if statuses:
            groups.append((_contains_any_of(sentence), tuple(statuses)))
    return tuple(groups)


# 已確認未滿足跨行資格條列時，依 any-of 或 all-of 回傳硬性不符。
def _group_exclusion(text: str, owned: set[str]) -> str | None:
    for any_of, statuses in _required_status_groups(text):
        if any_of:
            if any(_owns_status(owned, status) for status in statuses):
                continue
            return f"須具備以下任一身分：{'、'.join(statuses)}。"
        missing = tuple(status for status in statuses if not _owns_status(owned, status))
        if missing:
            return f"公告限定「{missing[0]}」身分。"
    return None


# 判斷文字是否為後續條列的資格標題。
def _is_group_header(text: str) -> bool:
    return _contains_requirement(text) and any(word in text for word in _GROUP_HEADER_WORDS)


# 標題直接以特定身分命名且非優先條件時視為必要資格。
def _title_exclusion(title: str, owned: set[str]) -> str | None:
    if _contains_preference(title) or _contains_ambiguous(title):
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


# 判斷文字是否只是排序、加分或非必要條件。
def _contains_preference(text: str) -> bool:
    return any(word in text for word in PREFERENCE_WORDS)


# 判斷文字是否暗示弱勢導向，但未明確說明一般生能否申請。
def _contains_ambiguous(text: str) -> bool:
    return any(word in text for word in AMBIGUOUS_WORDS)


# 判斷句子是否明確要求多個身分中的任一項。
def _contains_any_of(text: str) -> bool:
    return any(word in text for word in ANY_OF_WORDS)


# 保留單一條件句的語意範圍，避免跨段合併不同身分要求。
def _sentences(text: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for item in re.split(r"[。；;\n]", text)
        if (normalized := " ".join(item.split()))
    )