# -*- coding: utf-8 -*-

from dataclasses import replace

from config import UNRESOLVED_ATTACHMENT_MARKER
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityEvaluator,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 建立二年級進修部電子系測試背景。
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


# 建立測試公告。
def _item(title: str) -> Scholarship:
    return Scholarship.from_raw("lhu", title, "2026-07-27", "https://example.com/item")


# 掃描型附件未解析時，即使領域相符也只能待確認。
def test_unresolved_attachment_downgrades_field_match_to_review() -> None:
    detail = f"申請資格請參閱附件。{UNRESOLVED_ATTACHMENT_MARKER}"
    decision = EligibilityEvaluator().evaluate(
        _item("台灣電力與能源工程協會獎學金"), detail, _profile(),
    )

    assert decision.status == REVIEW
    assert "附件尚未成功解析" in decision.reason_text()


# 新住民子女專屬獎學金在身分不符時排除。
def test_new_immigrant_child_status_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("新住民子女獎學金"), "電子工程相關科系可申請。", _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "新住民子女" in decision.reason_text()


# 二年級學生不符合畢業生專屬獎學金。
def test_graduating_class_notice_is_ineligible_for_second_year() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("本校115級畢業生群育績優獎學金申請"),
        "請欲申請本獎學金之應屆(115級)畢業生提出資料。",
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "畢業年級" in decision.reason_text()


# 標題只有「大學生」不能單獨證明符合資格。
def test_general_student_title_without_qualification_context_is_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("寶佳大學生獎學金"), "相關資訊請自行下載。", _profile(),
    )

    assert decision.status == REVIEW


# 一般大專生出現在申請資格句型時可作為符合證據。
def test_general_college_qualification_context_is_eligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("一般優秀學生獎學金"),
        "申請對象為大專院校在校生，均可提出申請。",
        _profile(),
    )

    assert decision.status == ELIGIBLE


# profile 未填成績時應待確認，不得把缺值當成零分。
def test_missing_profile_grade_is_review_not_ineligible() -> None:
    profile = replace(_profile(), average_grade=0)
    decision = EligibilityEvaluator().evaluate(
        _item("高成就獎學金"),
        "申請人學業平均成績 80 分以上。",
        profile,
    )

    assert decision.status == REVIEW
    assert "未填學業平均" in decision.reason_text()
