# -*- coding: utf-8 -*-

import re

from config import UNRESOLVED_ATTACHMENT_MARKER
from src.profiles.student_profile import StudentProfile

GENERAL_COLLEGE_REASON = "公告適用一般大專在校生，未發現明確排除條件。"
GRADUATION_TERMS = (
    "應屆畢業生",
    "應屆畢業",
    "畢業班",
    "畢業年級",
    "級畢業生",
)


# 收集附件、畢業年級與個人資料缺值造成的待確認理由。
def find_safety_unknowns(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if UNRESOLVED_ATTACHMENT_MARKER in text:
        reasons.append("公告附件尚未成功解析，資格無法完整確認。")
    reasons.extend(_missing_score_reasons(text, profile))
    return reasons


# 二年級等非畢業年級學生遇到畢業生專屬公告時排除。
def find_graduation_exclusions(title: str, text: str, profile: StudentProfile) -> list[str]:
    if profile.year >= 4:
        return []
    if _title_requires_graduation(title) or _text_requires_graduation(text):
        return ["公告限定應屆或畢業年級學生。"]
    return []


# 缺少成績資料時移除把 0 分當成真實成績產生的排除理由。
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


# 只有申請資格語境中的一般大專生文字才能作為符合證據。
def filter_general_college_matches(matches: list[str], text: str) -> list[str]:
    contextual = _has_general_college_context(text)
    return [
        reason
        for reason in matches
        if reason != GENERAL_COLLEGE_REASON or contextual
    ]


# 從公告文字擷取缺少的學業或操行成績資料。
def _missing_score_reasons(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if profile.average_grade <= 0 and _extract_score(text, ("學業平均", "平均成績", "學業成績")):
        reasons.append("公告有學業成績門檻，但 profile.json 未填學業平均。")
    if profile.conduct_grade <= 0 and _extract_score(text, ("操行成績", "操行")):
        reasons.append("公告有操行成績門檻，但 profile.json 未填操行成績。")
    return reasons


# 判斷標題是否明確為畢業年級專屬獎助學金。
def _title_requires_graduation(title: str) -> bool:
    awards = ("獎學金", "助學金", "獎勵", "申請")
    has_term = any(term in title for term in GRADUATION_TERMS)
    return has_term and any(word in title for word in awards)


# 判斷正文是否以申請資格語氣限定畢業年級。
def _text_requires_graduation(text: str) -> bool:
    term = r"(?:應屆(?:\(\d{3}級\))?畢業生|\d{3}級畢業生|畢業班學生|畢業年級學生)"
    patterns = (
        rf"(?:限|僅限|只限|申請資格|申請對象).{{0,24}}{term}",
        rf"(?:欲申請|申請本獎學金).{{0,24}}{term}",
        rf"{term}.{{0,16}}(?:始得|方可|可申請|提出申請)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


# 判斷一般大專生詞是否位於申請資格句型中。
def _has_general_college_context(text: str) -> bool:
    terms = r"(?:大專院校學生|大專校院學生|大專院校在校生|大專校院在校生|大專在校生|大學生|在校學生)"
    patterns = (
        rf"(?:申請資格|申請對象|申請人|凡|限|僅限).{{0,30}}{terms}",
        rf"{terms}.{{0,20}}(?:均可申請|可申請|得申請|申請資格)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


# 擷取最低成績門檻，供缺值判斷使用。
def _extract_score(text: str, labels: tuple[str, ...]) -> float | None:
    label = "|".join(re.escape(item) for item in labels)
    score = r"(\d{1,3}(?:\.\d+)?)"
    patterns = (
        rf"(?:{label}).{{0,12}}?{score}\s*分?\s*(?:以上|或以上)",
        rf"(?:{label}).{{0,12}}?(?:不得低於|至少|須達|需達|達)\s*{score}\s*分?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None
