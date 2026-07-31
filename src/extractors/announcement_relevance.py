# -*- coding: utf-8 -*-

import re
import unicodedata

_RELEVANCE_SIGNALS = (
    "申請資格",
    "申請對象",
    "申請期間",
    "申請辦法",
    "截止",
    "應備文件",
    "獎學金",
    "助學金",
    "獎助學金",
    "補助金額",
    "獎勵金",
    "學年度",
    "學年",
)
_GENERIC_TITLE_TERMS = (
    "獎學金",
    "助學金",
    "獎助學金",
    "補助計畫",
    "補助",
    "申請公告",
    "申請事宜",
    "申請辦法",
    "實施計畫",
    "實施辦法",
    "相關事宜",
    "公告",
    "轉知",
)


# 驗證正文或主要辦法是否與公告標題及獎助申請語境一致。
def content_matches_announcement(
    title: str,
    body_text: str,
    rules_texts: list[str] | tuple[str, ...] = tuple(),
) -> bool:
    combined = "\n".join([body_text, *rules_texts]).strip()
    if not combined:
        return False
    normalized_content = _normalize(combined)
    normalized_title = _normalize(_strip_prefix(title))
    if len(normalized_title) >= 6 and normalized_title in normalized_content:
        return True
    hits = sum(signal in combined for signal in _RELEVANCE_SIGNALS)
    if hits >= 2:
        return True
    anchors = _title_anchors(title)
    return hits >= 1 and any(anchor in normalized_content for anchor in anchors)


# 移除轉知與括號型公告前綴，保留真正名稱。
def _strip_prefix(title: str) -> str:
    value = unicodedata.normalize("NFKC", title)
    value = re.sub(r"^[【〖\[][^】〗\]]{1,24}[】〗\]]\s*", "", value)
    return re.sub(r"^(?:轉知|公告|有關|函轉)+[：:－\-｜|\s]*", "", value)


# 從公告名稱建立具識別力的四字片段。
def _title_anchors(title: str) -> tuple[str, ...]:
    value = _strip_prefix(title)
    value = re.sub(r"(?:民國)?(?:20\d{2}|\d{3})年(?:度)?", " ", value)
    value = re.sub(r"\d{2,4}學年度(?:第\d學期)?", " ", value)
    for term in _GENERIC_TITLE_TERMS:
        value = value.replace(term, " ")
    compact = _normalize(value)
    if len(compact) < 4:
        return tuple()
    if len(compact) <= 8:
        return (compact,)
    return tuple(dict.fromkeys(compact[index : index + 4] for index in range(len(compact) - 3)))


# 以 NFKC、大小寫折疊與去除標點建立比對字串。
def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", " ".join(text.split())).casefold()
    return re.sub(r"[\W_]+", "", value)
