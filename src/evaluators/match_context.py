# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

FIELD_REASON = "公告領域與電子／電力相關背景相符。"
SCHOOL_REASON = "公告適用學校與目前就讀學校相符。"
DEPARTMENT_REASON = "公告指定科系與目前科系相符。"
FIELD_CONTEXT = ("科系", "學系", "系所", "領域", "主修", "專業", "研究", "相關科")
QUALIFICATION_CONTEXT = ("申請", "資格", "對象", "限", "就讀", "在校生")
NOISE_TERMS = ("電子郵件", "電子信箱", "電子檔", "電子化")


# 移除缺乏申請語境的學校、科系與領域匹配理由。
def filter_contextual_matches(
    matches: list[str],
    title: str,
    detail_text: str,
    profile: StudentProfile,
) -> list[str]:
    checks = {
        FIELD_REASON: _has_field_context(title, detail_text, profile),
        SCHOOL_REASON: _has_term_context(title, detail_text, profile.school),
        DEPARTMENT_REASON: _has_term_context(title, detail_text, profile.department),
    }
    return [reason for reason in matches if checks.get(reason, True)]


# 判斷專業關鍵字是否出現在標題或資格語境中。
def _has_field_context(title: str, detail_text: str, profile: StudentProfile) -> bool:
    keywords = set(profile.research_keywords) | {"電子", "電機", "電力", "能源"}
    clean_title = _remove_noise(title)
    if any(keyword and keyword in clean_title for keyword in keywords):
        return True
    return any(_keyword_has_context(detail_text, keyword) for keyword in keywords if keyword)


# 判斷學校或科系名稱是否出現在資格語境中。
def _has_term_context(title: str, detail_text: str, term: str) -> bool:
    if not term:
        return False
    if term in title:
        return True
    return any(
        term in sentence and any(marker in sentence for marker in QUALIFICATION_CONTEXT)
        for sentence in _sentences(detail_text)
    )


# 判斷專業詞附近是否同時有科系、領域或研究語境。
def _keyword_has_context(text: str, keyword: str) -> bool:
    for sentence in _sentences(_remove_noise(text)):
        if keyword not in sentence:
            continue
        if any(context in sentence for context in FIELD_CONTEXT):
            return True
    return False


# 移除電子郵件等不代表專業領域的固定雜訊。
def _remove_noise(text: str) -> str:
    cleaned = text
    for term in NOISE_TERMS:
        cleaned = cleaned.replace(term, "")
    return cleaned


# 依標點切分文字，避免跨句組合出錯誤語境。
def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。；;\n]", text) if item.strip()]
