# -*- coding: utf-8 -*-

from datetime import date

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_DISCOVERED_UNRESOLVED
from src.evaluators.eligibility_evaluator import INELIGIBLE, REVIEW, EligibilityEvaluator
from src.evaluators.runtime_safety import (
    DEADLINE_UNKNOWN,
    EVERGREEN,
    EXPIRED,
    OPEN,
    STALE_UNKNOWN,
    UPCOMING,
    classify_application_period,
    extract_application_deadline,
    find_deadline_exclusions,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電力", "能源"),
    )


def _item(title: str = "測試獎學金", published: str = "2026-06-30") -> Scholarship:
    return Scholarship.from_raw("fixture", title, published, "https://example.com/item")


def test_extract_deadline_uses_published_year() -> None:
    deadline = extract_application_deadline("請於7/24前交至課指組，逾期不受理。", "2026-06-30")
    assert deadline == date(2026, 7, 24)


def test_extract_deadline_supports_roc_slash_range() -> None:
    text = "申請期間：115/03/10~115/04/20，請至協會網站登錄提出申請。"
    assert extract_application_deadline(text, "2026-03-19") == date(2026, 4, 20)


def test_non_application_activity_date_is_ignored() -> None:
    text = "申請時間：即日起至額滿為止。職涯輔導時間：115年3月至6月12日止。"
    assert extract_application_deadline(text, "2026-03-05") is None


def test_applicant_deadline_precedes_school_review_date() -> None:
    text = "線上申請自115年4月1日至4月20日止。校方覆核至5月22日止。"
    assert extract_application_deadline(text, "2026-03-19") == date(2026, 4, 20)


def test_application_period_is_upcoming() -> None:
    period = classify_application_period(
        "申請期間：115/08/03至115/09/11止。",
        "2026-06-09",
        today=date(2026, 7, 28),
    )
    assert period.status == UPCOMING
    assert period.start_date == date(2026, 8, 3)
    assert period.deadline == date(2026, 9, 11)


def test_application_period_is_open() -> None:
    period = classify_application_period(
        "申請期間：115/07/01至115/09/11止。",
        "2026-06-09",
        today=date(2026, 7, 28),
    )
    assert period.status == OPEN


def test_application_period_is_expired() -> None:
    period = classify_application_period(
        "請於7/24前交至課指組，逾期不受理。",
        "2026-06-30",
        today=date(2026, 7, 28),
    )
    assert period.status == EXPIRED


def test_application_period_keeps_recent_unknown_deadline() -> None:
    period = classify_application_period(
        "相關資訊請自行下載，並於申請截止日前完成申請。",
        "2026-07-06",
        today=date(2026, 7, 28),
    )
    assert period.status == DEADLINE_UNKNOWN


def test_old_unknown_without_current_year_is_stale() -> None:
    period = classify_application_period(
        "相關資訊請自行下載，並於申請截止日前完成申請。",
        "2025-07-01",
        today=date(2026, 8, 1),
    )
    assert period.status == STALE_UNKNOWN


def test_old_notice_with_current_year_stays_current_unknown() -> None:
    period = classify_application_period(
        "2026年度仍受理申請，詳細期限請見附件。",
        "2025-07-01",
        today=date(2026, 8, 1),
    )
    assert period.status == DEADLINE_UNKNOWN


def test_evergreen_program_is_actionable() -> None:
    period = classify_application_period(
        "本計畫全年受理，申請資格與申請方式如下。",
        "2024-01-01",
        today=date(2026, 8, 1),
    )
    assert period.status == EVERGREEN


def test_expired_application_is_ineligible() -> None:
    reasons = find_deadline_exclusions(
        _item(),
        "請於7/24前交至課指組，逾期不受理。",
        today=date(2026, 7, 27),
    )
    assert reasons == ["申請截止日 2026-07-24 已過，不推播。"]


def test_stale_unknown_is_excluded() -> None:
    reasons = find_deadline_exclusions(
        _item(published="2025-01-01"),
        "申請資格請參閱附件。",
        today=date(2026, 8, 1),
    )
    assert reasons == ["公告發布時間已久且無當年度申請證據，列為歷史期限未知。"]


def test_full_time_student_requirement_stays_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("電力工程獎學金", "2026-07-27"),
        "申請對象限於大學生及研究所全職學生，限電力相關科系。",
        _profile(),
    )
    assert decision.status == REVIEW
    assert "全職學生" in decision.reason_text()


def test_unresolved_rules_ignore_body_graduate_noise() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("儒鴻教育獎助學金", "2026-07-27"),
        "基金會業務包含研究生獎學金與博士班合作。",
        _profile(),
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
    )
    assert decision.status == REVIEW


def test_gemini_moves_department_out_of_program_type() -> None:
    extraction = GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        degree_levels=["高中、高職、專科、學院、大學、研究所(僅限碩士)"],
        program_types_included=["機械科系"],
        evidence=[{"page": 1, "text": "大學限於機械科系之學生。"}],
    )
    assert extraction.program_types_included == []
    assert extraction.departments_included == ["機械科系"]
    assert "大學生" in extraction.degree_levels
    assert "研究生" in extraction.degree_levels


def test_normalized_gemini_mechanical_scope_is_ineligible() -> None:
    extraction = GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        degree_levels=["大學"],
        program_types_included=["機械科系"],
        evidence=[{"page": 1, "text": "大學限於機械科系之學生。"}],
    )
    decision = EligibilityEvaluator().evaluate(
        _item("星隆獎學金", "2026-07-27"),
        extraction.to_rule_text(),
        _profile(),
    )
    assert decision.status == INELIGIBLE
    assert "機械" in decision.reason_text()
