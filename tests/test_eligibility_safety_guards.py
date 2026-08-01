# -*- coding: utf-8 -*-

from dataclasses import replace

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_DISCOVERED_UNRESOLVED
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityEvaluator,
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
        research_keywords=("電力電子", "能源"),
    )


def _item(title: str) -> Scholarship:
    return Scholarship.from_raw("lhu", title, "2026-07-27", "https://example.com/item")


def test_unresolved_attachment_downgrades_field_match_to_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("台灣電力與能源工程協會獎學金"),
        "申請資格請參閱附件。",
        _profile(),
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
    )

    assert decision.status == REVIEW
    assert "主要資格辦法尚未成功解析" in decision.reason_text()


def test_new_immigrant_child_status_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("新住民子女獎學金"), "電子工程相關科系可申請。", _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "新住民子女" in decision.reason_text()


def test_graduating_class_notice_is_ineligible_for_second_year() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("本校115級畢業生群育績優獎學金申請"),
        "請欲申請本獎學金之應屆(115級)畢業生提出資料。",
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "畢業年級" in decision.reason_text()


def test_general_student_title_without_qualification_context_is_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("寶佳大學生獎學金"), "相關資訊請自行下載。", _profile(),
    )

    assert decision.status == REVIEW


def test_general_college_qualification_context_is_eligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("一般優秀學生獎學金"),
        "申請對象為大專院校在校生，均可提出申請。",
        _profile(),
    )

    assert decision.status == ELIGIBLE


def test_missing_profile_grade_is_only_manual_check() -> None:
    profile = replace(_profile(), average_grade=0)
    decision = EligibilityEvaluator().evaluate(
        _item("高成就獎學金"),
        "申請人學業平均成績 80 分以上。",
        profile,
    )

    assert decision.status == REVIEW
    assert "未填學業平均" not in decision.reason_text()
    assert any("80" in item for item in decision.manual_checks)
