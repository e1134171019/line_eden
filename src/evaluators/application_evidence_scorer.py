# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

VALID_APPLICATION_DETAIL = "valid_application_detail"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
NAVIGATION_OR_WRONG_PAGE = "navigation_or_wrong_page"
SOURCE_ERROR = "source_error"

_EVIDENCE_RULES: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (
        (
            "申請資格",
            "申請對象",
            "申請人資格",
            "申請條件",
            "資格條件",
            "適用對象",
            "濟助對象",
        ),
        2,
        "申請資格",
    ),
    (("申請期間", "申請日期", "受理期間", "報名期間"), 2, "申請期間"),
    (("截止日期", "申請截止", "收件截止", "報名截止"), 2, "截止日期"),
    (("申請方式", "報名方式", "送件方式", "申辦方式"), 2, "申請方式"),
    (("檢附文件", "應備文件", "繳交文件", "申請文件", "應備資料"), 1, "檢附文件"),
    (("申請表", "線上報名", "線上申請", "報名表"), 1, "申請表或線上申請"),
    (("獎助金額", "獎學金額", "補助金額", "濟助金額", "每名核發"), 1, "獎助金額"),
)
_APPLICANT_SCOPE = re.compile(
    r"(?:大專(?:院校|校院)?|大學|學士|研究所|研究生|高中職|高中|高職|五專|國中|在校生|學生|新生)"
    r".{0,40}?(?:可申請|得申請|均可申請|提出申請|申請本|申請對象|濟助對象)"
)
_APPLICATION_ACTION = re.compile(
    r"(?:可申請|得申請|提出申請|開放申請|受理申請|辦理申請|申請方式)"
)


@dataclass(frozen=True)
class ApplicationEvidence:
    """正文是否足以代表可申請公告的可解釋評分。"""

    score: int
    status: str
    hits: tuple[str, ...]


def score_application_evidence(text: str, *, source_error: bool = False) -> ApplicationEvidence:
    """依申請資格、期間、方式與明確適用對象評分。"""

    if source_error:
        return ApplicationEvidence(0, SOURCE_ERROR, tuple())
    normalized = " ".join(text.split())
    score = 0
    hits: list[str] = []
    for terms, weight, label in _EVIDENCE_RULES:
        if any(term in normalized for term in terms):
            score += weight
            hits.append(label)
    has_scope = bool(_APPLICANT_SCOPE.search(normalized))
    has_action = bool(_APPLICATION_ACTION.search(normalized))
    if has_scope:
        score += 2
        hits.append("適用對象")
    if has_action:
        score += 1
        hits.append("申請行動")
    if score >= 4 or (has_scope and has_action):
        status = VALID_APPLICATION_DETAIL
    elif score >= 2:
        status = INSUFFICIENT_EVIDENCE
    else:
        status = NAVIGATION_OR_WRONG_PAGE
    return ApplicationEvidence(score, status, tuple(dict.fromkeys(hits)))
