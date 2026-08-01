# -*- coding: utf-8 -*-

from dataclasses import dataclass

VALID_APPLICATION_DETAIL = "valid_application_detail"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
NAVIGATION_OR_WRONG_PAGE = "navigation_or_wrong_page"
SOURCE_ERROR = "source_error"

_EVIDENCE_RULES: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (("申請資格", "申請對象", "申請人資格"), 2, "申請資格"),
    (("申請期間", "申請日期", "受理期間", "報名期間"), 2, "申請期間"),
    (("截止日期", "申請截止", "收件截止", "報名截止"), 2, "截止日期"),
    (("申請方式", "報名方式", "送件方式", "申辦方式"), 2, "申請方式"),
    (("檢附文件", "應備文件", "繳交文件", "申請文件"), 1, "檢附文件"),
    (("申請表", "線上報名", "線上申請", "報名表"), 1, "申請表或線上申請"),
    (("獎助金額", "獎學金額", "補助金額", "每名核發"), 1, "獎助金額"),
)


@dataclass(frozen=True)
class ApplicationEvidence:
    """正文是否足以代表可申請公告的可解釋評分。"""

    score: int
    status: str
    hits: tuple[str, ...]


def score_application_evidence(text: str, *, source_error: bool = False) -> ApplicationEvidence:
    """依申請資格、期間、方式等正文證據評分，不使用模型猜測。"""

    if source_error:
        return ApplicationEvidence(0, SOURCE_ERROR, tuple())
    normalized = " ".join(text.split())
    score = 0
    hits: list[str] = []
    for terms, weight, label in _EVIDENCE_RULES:
        if any(term in normalized for term in terms):
            score += weight
            hits.append(label)
    if score >= 4:
        status = VALID_APPLICATION_DETAIL
    elif score >= 2:
        status = INSUFFICIENT_EVIDENCE
    else:
        status = NAVIGATION_OR_WRONG_PAGE
    return ApplicationEvidence(score, status, tuple(hits))
