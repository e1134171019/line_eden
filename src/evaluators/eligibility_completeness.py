# -*- coding: utf-8 -*-

import re

from src.evaluators.eligibility_safety_rules import GENERAL_COLLEGE_REASON
from src.evaluators.match_context import DEPARTMENT_REASON, FIELD_REASON, SCHOOL_REASON
from src.profiles.student_profile import StudentProfile

SCOPE_REASONS = {
    GENERAL_COLLEGE_REASON,
    FIELD_REASON,
    SCHOOL_REASON,
    DEPARTMENT_REASON,
    "公告明確包含進修部學生。",
}
INCOMPATIBLE_DEPARTMENT_TERMS = (
    "大眾傳播",
    "新聞",
    "傳播",
    "觀光",
    "餐旅",
    "護理",
    "醫學",
    "法律",
    "社會工作",
    "人文",
    "藝術",
    "體育",
    "商管",
    "會計",
    "財金",
    "中文",
    "外文",
    "機械",
)


# 展開常見縮寫並統一大專在學用語，避免同義句型漏判。
def normalize_eligibility_text(text: str) -> str:
    normalized = re.sub(
        r"低\s*[\(（]\s*中低\s*[\)）]\s*收入戶",
        "低收入戶及中低收入戶",
        text,
    )
    normalized = normalized.replace("大專院校在學生", "大專院校在校生")
    normalized = normalized.replace("大專校院在學生", "大專校院在校生")
    normalized = normalized.replace("大學院校在學生", "大專院校在校生")
    normalized = normalized.replace("大學院校學生", "大專院校學生")
    return " ".join(normalized.split())


# 補足既有規則尚未涵蓋的學制、學位與科系硬性排除。
def find_hard_exclusions(
    title: str,
    text: str,
    profile: StudentProfile,
) -> list[str]:
    reasons = _program_exclusions(text, profile)
    reasons.extend(_degree_exclusions(title, text, profile))
    reasons.extend(_department_exclusions(text, profile))
    return list(dict.fromkeys(reasons))


# 只有至少一項適用對象已確認時，正向門檻才足以成為 eligible。
def find_completeness_unknowns(matches: list[str]) -> list[str]:
    if matches and not any(reason in SCOPE_REASONS for reason in matches):
        return ["僅確認成績、排名或戶籍門檻，尚未確認公告適用對象。"]
    return []


# 判斷公告是否明確排除進修或在職身分。
def _program_exclusions(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if "進修" in profile.program_type and _explicitly_excludes(
        text,
        ("進修部", "進修推廣部", "進修學士班", "進修學制"),
    ):
        reasons.append("公告明確排除進修部或進修推廣學制。")
    if profile.employed and _explicitly_excludes(
        text,
        ("在職專班", "在職班", "在職學生", "在職者"),
    ):
        reasons.append("公告明確排除在職專班或在職學生。")
    return reasons


# 學士生遇到國高中以下或研究所專屬公告時直接排除。
def _degree_exclusions(title: str, text: str, profile: StudentProfile) -> list[str]:
    if profile.degree_level != "學士":
        return []
    if _is_school_level_only(text):
        return ["公告限定非大專學制。"]
    graduate_terms = ("博士生", "博士班", "碩士生", "碩士班", "研究生", "碩博士")
    bachelor_terms = ("大學生", "大學部", "學士班", "大專學生", "大專在校生")
    title_limited = _title_is_graduate_only(title, graduate_terms, bachelor_terms)
    text_limited = any(
        _sentence_requires_group(sentence, graduate_terms)
        and not any(term in sentence for term in bachelor_terms)
        for sentence in _sentences(text)
    )
    if title_limited or text_limited:
        return ["公告限定研究所或博士生層級。"]
    return []


# 僅列國小、國中、高中或高職，且未同列大專層級時視為非大專專屬。
def _is_school_level_only(text: str) -> bool:
    school_terms = ("國小", "國中", "高中", "高職")
    college_terms = ("大專", "大學", "學士")
    return any(
        _sentence_requires_group(sentence, school_terms)
        and not any(term in sentence for term in college_terms)
        for sentence in _sentences(text)
    )


# 只有每個獎項片段都含研究生詞時，標題才代表研究所專屬。
def _title_is_graduate_only(
    title: str,
    graduate_terms: tuple[str, ...],
    bachelor_terms: tuple[str, ...],
) -> bool:
    if any(term in title for term in bachelor_terms):
        return False
    segments = [
        segment.strip()
        for segment in re.split(r"[、,，/]|(?:及|與)", title)
        if segment.strip()
    ]
    award_segments = [
        segment
        for segment in segments
        if any(marker in segment for marker in ("獎", "補助", "申請"))
    ]
    return bool(award_segments) and all(
        any(term in segment for term in graduate_terms)
        for segment in award_segments
    )


# 電子工程背景遇到明確限定不相容科系的資格句時直接排除。
def _department_exclusions(text: str, profile: StudentProfile) -> list[str]:
    compatible = _compatible_department_terms(profile)
    for sentence in _sentences(text):
        if not _has_department_requirement_context(sentence):
            continue
        incompatible = next(
            (term for term in INCOMPATIBLE_DEPARTMENT_TERMS if term in sentence),
            None,
        )
        if incompatible and not any(term in sentence for term in compatible):
            return [f"公告限定「{incompatible}」相關科系，與目前科系不符。"]
    return []


# 建立目前背景可接受的科系與廣義工程領域詞。
def _compatible_department_terms(profile: StudentProfile) -> set[str]:
    terms = set(profile.research_keywords)
    terms.update(
        (
            profile.department,
            "電子",
            "電機",
            "電力",
            "能源",
            "工程",
            "理工",
            "電資",
            "資通訊",
        )
    )
    return {term for term in terms if term}


# 判斷句子是否正在描述必要科系資格。
def _has_department_requirement_context(sentence: str) -> bool:
    has_department = any(term in sentence for term in ("相關系所", "相關科系", "相關學系"))
    has_requirement = any(
        marker in sentence
        for marker in ("申請資格", "申請對象", "限", "僅限", "就讀", "在學")
    )
    return has_department and has_requirement


# 判斷指定族群是否位於必要申請資格句型。
def _sentence_requires_group(sentence: str, terms: tuple[str, ...]) -> bool:
    pattern = "|".join(re.escape(term) for term in terms)
    prefix = rf"(?:限|僅限|只限|申請對象|申請資格|資格限於).{{0,24}}(?:{pattern})"
    suffix = rf"(?:{pattern}).{{0,16}}(?:始得|方可|才可|可申請)"
    return bool(re.search(prefix, sentence) or re.search(suffix, sentence))


# 判斷指定對象是否被公告明確排除。
def _explicitly_excludes(text: str, terms: tuple[str, ...]) -> bool:
    pattern = "|".join(re.escape(term) for term in terms)
    prefix = rf"(?:不含|不包括|不受理|不接受|排除|不得為).{{0,18}}(?:{pattern})"
    suffix = rf"(?:{pattern}).{{0,18}}(?:不得申請|不予受理|不適用)"
    return bool(re.search(prefix, text) or re.search(suffix, text))


# 依標點切分句子，避免跨句拼接出不存在的限制。
def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。；;\n]", text) if item.strip()]