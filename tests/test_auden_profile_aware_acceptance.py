# -*- coding: utf-8 -*-

from dataclasses import replace

from src.automation.release_acceptance import evaluate_release_acceptance
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.evaluators.eligibility_evaluator import INELIGIBLE, EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.services.scholarship_service import AuditRecord, AuditResult

AUDEN = "auden-university-talent"
SONGLIANG = "songliang-aid"


def _profile(**updates: object) -> StudentProfile:
    values: dict[str, object] = {
        "school": "測試大學",
        "degree_level": "學士",
        "program_type": "日間部",
        "department": "測試系",
        "year": 2,
        "employed": False,
        "average_grade": 80.0,
        "conduct_grade": 90,
        "class_rank": 5,
        "class_size": 50,
        "residence": "測試市",
        "special_statuses": tuple(),
        "research_keywords": ("電子",),
        "nationality": "",
        "enrollment_status": "",
        "credits_earned": 60,
        "residence_years": 1.0,
        "cumulative_average": 80.0,
        "academic_year_average": 80.0,
        "latest_semester_average": 80.0,
        "latest_conduct_grade": 90,
        "latest_class_rank": 5,
        "latest_class_size": 50,
        "has_failed_courses": False,
        "has_major_discipline": False,
        "household_income": None,
        "household_size": 3,
        "has_received_similar_scholarship": None,
        "can_obtain_recommendation": True,
        "has_student_loan": False,
        "has_qualifying_volunteer_service": None,
        "birth_date": "",
    }
    values.update(updates)
    return StudentProfile(**values)  # type: ignore[arg-type]


def _fetch_result() -> DetailFetchResult:
    diagnostic = ResourceDiagnostic(
        "source",
        "https://example.test/detail",
        "https://example.test/detail",
        "text/html",
        100,
        "html",
        "success",
        100,
    )
    return DetailFetchResult("rules", diagnostic, tuple(), 0, body_text="rules")


def _record(
    program_id: str,
    hard_status: str,
    *,
    notice_kind: str,
    action_status: str,
    application_status: str = "open",
) -> AuditRecord:
    item = Scholarship.from_raw(
        f"tun-program-{program_id}",
        program_id,
        "2026-08-12",
        "https://example.test/detail",
        program_id=program_id,
    )
    item = replace(
        item,
        notice_kind=notice_kind,
        application_status=application_status,
        resolution_status="valid_application_detail",
        eligibility_status=hard_status,
        hard_eligibility_status=hard_status,
        action_status=action_status,
    )
    return AuditRecord(item, "rules", _fetch_result())


def _source_report() -> dict[str, object]:
    ids = [f"program-{index}" for index in range(36)] + [AUDEN, SONGLIANG]
    return {
        "program_states": [
            {"program_id": program_id, "status": "matched"}
            for program_id in ids
        ]
    }


def test_auden_2026_bachelor_average_below_threshold_is_hard_ineligible() -> None:
    item = Scholarship.from_raw(
        "fixture",
        "2026耀登炳南大專院校優秀人才獎學金",
        "2026-07-23",
        "https://www.auden.com.tw/2026scholarship/",
    )
    detail = (
        "申請對象：具有中華民國國籍，且為國內大專院校在學學生。\n"
        "成績計算方式：(以114學年上下學期或歷年畢業總成績為準)\n"
        "學士班：學期學科總平均分數85分以上且系所排名前10%者。\n"
        "上述申請者須無不及格科目，操行成績甲等或者80分以上。"
    )

    decision = EligibilityEvaluator().evaluate(item, detail, _profile())

    assert decision.status == INELIGIBLE
    assert "80" in decision.reason_text()
    assert "85" in decision.reason_text()


def test_release_acceptance_allows_auden_resolved_ineligible_decision() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        AuditResult(
            [
                _record(
                    AUDEN,
                    "ineligible",
                    notice_kind="application",
                    action_status="reject",
                ),
                _record(
                    SONGLIANG,
                    "ineligible",
                    notice_kind="policy",
                    action_status="not_actionable",
                    application_status="not_applicable",
                ),
            ],
            0,
            0,
            1,
            "audit",
        ),
    )

    assert result.passed is True, result.failures
