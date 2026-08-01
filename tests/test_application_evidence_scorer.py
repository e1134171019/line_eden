# -*- coding: utf-8 -*-

from src.evaluators.application_evidence_scorer import (
    INSUFFICIENT_EVIDENCE,
    NAVIGATION_OR_WRONG_PAGE,
    SOURCE_ERROR,
    VALID_APPLICATION_DETAIL,
    score_application_evidence,
)


def test_complete_application_detail_is_valid() -> None:
    evidence = score_application_evidence(
        "申請資格為大專院校在校生。申請期間至9月30日。"
        "申請方式採線上申請，並檢附文件。"
    )

    assert evidence.status == VALID_APPLICATION_DETAIL
    assert evidence.score >= 4
    assert "申請資格" in evidence.hits
    assert "申請方式" in evidence.hits


def test_partial_detail_is_insufficient() -> None:
    evidence = score_application_evidence("申請資格請參閱附件。")

    assert evidence.status == INSUFFICIENT_EVIDENCE
    assert evidence.score == 2


def test_navigation_page_is_not_application_detail() -> None:
    evidence = score_application_evidence("首頁 關於我們 最新消息 聯絡方式")

    assert evidence.status == NAVIGATION_OR_WRONG_PAGE
    assert evidence.score == 0


def test_source_error_is_explicit() -> None:
    evidence = score_application_evidence("", source_error=True)

    assert evidence.status == SOURCE_ERROR
    assert evidence.score == 0
