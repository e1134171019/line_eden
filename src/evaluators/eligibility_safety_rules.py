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


# 收集個人資料缺值造成的待確認理由。
def find_safety_unknowns(text: str, profile: StudentProfile) -> list[str]:
    return _missing_score_reasons(text, profile)


# 二年級等非畢業年級學生遇到畢業生專屬公告時排除。
def find_graduation_exclusions(
    title: str,
    text: str,
    profile: StudentProfile,
) -> list[str]:
    if profile.year >= 4:
        return []
    if _title_requires_graduation(title) or _text_requires_graduation(text):
        return ["公告限定應屆或畢業年級學生。"]
    return []


# 缺少成績資料時，不把 0 分視為真實成績。
def filter_missing_score_exclusions(
    exclusions: list[str],
    profile: StudentProfile,
) -> list[str]:
    filtered: list[str] = []
    for reason in exclusions:
        if reason.startswith("學業平均未達") and profile.average_grade <= 0:
            continue
        if reason.startswith("操行成績未達") and profile.conduct_grade <= 0:
            continue
        filtered.append(reason)
    return filtered


# 只有申請或補助資格語境中的一般大專生文字才能作為符合證據。
def filter_general_college_matches(matches: list[str], text: str) -> list[str]:
    contextual = _has_general_college_context(text)
    filtered = [
        reason
        for reason in matches
        if reason != GENERAL_COLLEGE_REASON or contextual
    ]
    if contextual and GENERAL_COLLEGE_REASON not in filtered:
        filtered.append(GENERAL_COLLEGE_REASON)
    return filtered


# 檢查成績欄位是否因 profile 缺值而無法判斷。
def _missing_score_reasons(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if profile.average_grade <= 0 and _extract_score(
        text,
        ("學業平均", "平均成績", "學業成績"),
    ):
        reasons.append("公告有學業成績門檻，但 profile.json 未填學業平均。")
    if profile.conduct_grade <= 0 and _extract_score(text, ("操行成績", "操行")):
        reasons.append("公告有操行成績門檻，但 profile.json 未填操行成績。")
    return reasons


# 標題只有在獎助申請語境中提及畢業生，才視為畢業年級限制。
def _title_requires_graduation(title: str) -> bool:
    awards = ("獎學金", "助學金", "獎勵", "申請")
    has_term = any(term in title for term in GRADUATION_TERMS)
    return has_term and any(word in title for word in awards)


# 正文中的畢業生必須位於限制句型才構成排除。
def _text_requires_graduation(text: str) -> bool:
    term = r"(?:應屆(?:\(\d{3}級\))?畢業生|\d{3}級畢業生|畢業班學生|畢業年級學生)"
    patterns = (
        rf"(?:限|僅限|只限|申請資格|申請對象).{{0,24}}{term}",
        rf"(?:欲申請|申請本獎學金).{{0,24}}{term}",
        rf"{term}.{{0,16}}(?:始得|方可|可申請|提出申請)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


# 判斷一般大專學生字樣是否位於明確申請、補助或培育對象語境。
def _has_general_college_context(text: str) -> bool:
    terms = (
        r"(?:大專院校學生|大專校院學生|大專院校在校生|大專校院在校生|"
        r"大專院校在學學生|大專校院在學學生|大專在校生|大學生|在校學生)"
    )
    patterns = (
        rf"(?:申請資格|申請對象|補助對象|獎助對象|適用對象|培育對象|申請人|凡|限|僅限|全國公私立).{{0,30}}{terms}",
        rf"{terms}.{{0,20}}(?:均可申請|可申請|得申請|申請資格|為主)",
        rf"{terms}.{{0,6}}(?:之|的).{{0,24}}(?:學業|操行|成績|排名)",
        rf"{terms}.{{0,30}}(?:學業|平均成績|操行|排名)",
        r"(?:申請對象|適用對象|培育對象).{0,36}(?:大學校院|大專院校|大專校院).{0,24}大[二三四](?:含)?以上.{0,24}(?:在學生|在校生|學生)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


# 擷取指定成績門檻。
def _extract_score(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        match = re.search(rf"{label}.{{0,12}}?(\d{{1,3}}(?:\.\d+)?)\s*分?", text)
        if match:
            return float(match.group(1))
    return None