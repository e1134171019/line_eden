# -*- coding: utf-8 -*-

from config import ATTACHMENT_TEXT_MARKER, UNRESOLVED_ATTACHMENT_MARKER
from src.collectors.structured_announcement_detail_fetcher import (
    StructuredAnnouncementDetailFetcher,
)
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
)
from src.evaluators.eligibility_evaluator import REVIEW, EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


def _fetcher() -> StructuredAnnouncementDetailFetcher:
    return StructuredAnnouncementDetailFetcher(10.0, "test", 3, 1024 * 1024, 5)


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90,
        conduct_grade=85,
        class_rank=1,
        class_size=20,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電力"),
    )


def test_structured_fetcher_does_not_insert_marker_text() -> None:
    fetcher = _fetcher()

    combined = fetcher._combine_text(
        "正文原本就可能寫到附件內容四個字。",
        ["附件資格：電子工程相關科系。"],
    )
    unresolved = fetcher._apply_rules_status_marker(
        combined,
        RULES_STATUS_DISCOVERED_UNRESOLVED,
    )

    assert ATTACHMENT_TEXT_MARKER not in combined
    assert UNRESOLVED_ATTACHMENT_MARKER not in unresolved
    assert "附件資格" in combined


def test_notice_content_keeps_body_and_attachments_separate() -> None:
    source = ResourceDiagnostic(
        "source",
        "https://example.com",
        "https://example.com",
        "text/html",
        100,
        "html",
        "success",
        20,
    )
    attachment = ExtractedAttachment(
        "https://example.com/rules.pdf",
        "https://example.com/rules.pdf",
        "附件一",
        "generic_attachment",
        "scholarship_rules",
        "pdf",
        "success",
        "申請資格限電子工程相關科系。",
    )
    result = DetailFetchResult(
        "legacy combined text",
        source,
        tuple(),
        1,
        body_text="公告正文",
        extracted_attachments=(attachment,),
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
    )

    assert result.content.main_text == "公告正文"
    assert result.content.attachments == (attachment,)
    assert result.content.rules_status == RULES_STATUS_DISCOVERED_UNRESOLVED


def test_unresolved_rules_status_is_fail_closed_without_marker() -> None:
    item = Scholarship.from_raw(
        "lhu",
        "能源獎學金",
        "2026-07-28",
        "https://example.com/scholarship",
    )
    decision = EligibilityEvaluator().evaluate(
        item,
        "正文寫著電子工程相關科系、平均80分，但主要辦法尚未解析。",
        _profile(),
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
    )

    assert decision.status == REVIEW
    assert "主要資格辦法尚未成功解析" in decision.reason_text()
