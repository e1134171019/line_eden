# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

GENERAL_COLLEGE_REASON = "公告適用一般大專在校生，未發現明確排除條件。"
GRADUATION_TERMS = (
    "應屆畢業生",
    "應屆畢業",
    "畢業班",
    "畢業年級",
    "級畢業生",
)


def find_safety_unknowns(text: str, profile: StudentProfile) -> list[str]:
    """收集個人資料缺值造成的待確認理由。"""
    return _missing_score_reasons(text, profile)


def find_graduation_exclusions(title: str, text: str, profile: StudentProfile) -> list[str]:
    """二年級等非畢業年級學生遇到畢業生專屬公告時排除。"""
    if profile.year >= 4:
        return []
    if _title_requires_graduation(title) or _text_requires_graduation(text):
        return ["公告限定應屆或畢業年級學生。"]
    return []


def filter_missing_score_exclusions(
    exclusions: list[str],
    profile: StudentProfile,
) -> list[str]:
    """缺少成績資料時，不把 0 分視為真實成績。"""
    filtered: list[str] = []
    for reason in exclusions:
        if reason.startswith("學業平均未達") and profile.average_grade <= 0:
            continue
        if reason.startswith("操行成績未達") and profile.conduct_grade <= 0:
            continue
        filtered.append(reason)
    return filtered


def filter_general_college_matches(matches: list[str], text: str) -> list[str]:
    """只有申請資格語境中的一般大專生文字才能作為符合證據。"""
    contextual = _has_general_college_context(text)
    filtered = [
        reason
        for reason in matches
        if reason != GENERAL_COLLEGE_REASON or contextual
    ]
    if contextual and GENERAL_COLLEGE_REASON not in filtered:
        filtered.append(GENERAL_COLLEGE_REASON)
    return filtered


def _missing_score_reasons(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if profile.average_grade <= 0 and _extract_score(text, ("學業平均", "平均成績", "學業成績")):
        reasons.append("公告有學業成績門檻，但 profile.json 未填學業平均。")
    if profile.conduct_grade <= 0 and _extract_score(text, ("操行成績", "操行")):
        reasons.append("公告有操行成績門檻，但 profile.json 未填操行成績。")
    return reasons


def _title_requires_graduation(title: str) -> bool:
    awards = ("獎學金", "助學金", "獎勵", "申請")
    has_term = any(term in title for term in GRADUATION_TERMS)
    return has_term and any(word in title for word in awards)


def _text_requires_graduation(text: str) -> bool:
    term = r"(?:應屆(?:\(\d{3}級\))?畢業生|\d{3}級畢業生|畢業班學生|畢業年級學生)"
    patterns = (
        rf"(?:限|僅限|只限|申請資格|申請對象).{{0,24}}{term}",
        rf"(?:欲申請|申請本獎學金).{{0,24}}{term}",
        rf"{term}.{{0,16}}(?:始得|方可|可申請|提出申請)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _has_general_college_context(text: str) -> bool:
    terms = r"(?:大專院校學生|大專校院學生|大專院校在校生|大專校院在校生|大專在校生|大學生|在校學生)"
    patterns = (
        rf"(?:申請資格|申請對象|申請人|凡|限|僅限).{{0,30}}{terms}",
        rf"{terms}.{{0,20}}(?:均可申請|可申請|得申請|申請資格)",
        rf"{terms}.{{0,6}}(?:之|的).{{0,24}}(?:學業|操行|成績|排名)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _extract_score(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        match = re.search(rf"{label}.{{0,12}}?(\d{{1,3}}(?:\.\d+)?)\s*分?", text)
        if match:
            return float(match.group(1))
    return None
