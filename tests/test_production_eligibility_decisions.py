# -*- coding: utf-8 -*-

from src.collectors.decision_safe_tun_program_watch_collector import (
    _is_replaced_navigation_candidate,
)
from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_NOT_REQUIRED
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    EligibilityEvaluator,
)
from src.models.evaluator_input import EvaluatorInput
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.catalogs.tun_program_sources import resolved_programs


def _profile() -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部四技",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.6,
        conduct_grade=86.0,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電機", "電力", "能源", "資通訊"),
        nationality="中華民國",
        enrollment_status="在學",
        academic_year_average=90.34,
        latest_semester_average=90.6,
        latest_conduct_grade=86.0,
        latest_class_rank=1,
        latest_class_size=17,
        has_failed_courses=False,
        has_major_discipline=False,
        special_statuses_confirmed=True,
    )


def _scholarship(program_id: str, title: str, url: str) -> Scholarship:
    return Scholarship.from_raw(
        source=f"production-{program_id}",
        title=title,
        published_date="2026-07-23",
        source_url=url,
        entry_url=url,
        detail_url=url,
        program_id=program_id,
    )


# 耀登同段先包含學士／碩士／博士，再排除學士一年級新生；大二不得被錯殺。
def test_auden_excluded_freshman_subgroup_does_not_become_required_year() -> None:
    scholarship = _scholarship(
        "auden-university-talent",
        "2026耀登炳南大專院校優秀人才獎學金",
        "https://www.auden.com.tw/2026scholarship/",
    )
    text = (
        "貳、申請對象。具有中華民國國籍。就讀國內已立案大專院校資通訊、"
        "生醫工程及環境永續相關系所之修業年限學士班、碩士班及博士班在學學生，"
        "不含學士班一年級新生、休學生、延畢生、學分班及空中大學學生。"
        "學士班學期學科總平均分數85分以上且系所排名前10%，無不及格科目，"
        "操行成績80分以上。備註：一年級新生以前一學歷之歷年畢業總成績為準；"
        "非一年級新生，現讀二年級含以上在學學生，以114學年上下學期總成績為準。"
    )

    decision = EligibilityEvaluator().evaluate(
        scholarship,
        EvaluatorInput(body_text=text, rules_status=RULES_STATUS_NOT_REQUIRED),
        _profile(),
    )

    assert decision.status == ELIGIBLE
    assert "公告限定新生或大一學生。" not in decision.reasons


# 真正明文只收大一或新生時，年級排除仍必須有效。
def test_explicit_freshman_only_program_remains_ineligible() -> None:
    scholarship = _scholarship(
        "freshman-only",
        "大一新生獎學金",
        "https://example.test/freshman",
    )
    decision = EligibilityEvaluator().evaluate(
        scholarship,
        EvaluatorInput(
            body_text="申請資格限大學一年級新生。",
            rules_status=RULES_STATUS_NOT_REQUIRED,
        ),
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "公告限定新生或大一學生。" in decision.reasons


# 松樑 force-replace 後，正式辦法頁回連的舊導覽入口不得成為申請公告。
def test_songliang_old_navigation_candidate_is_removed() -> None:
    source = next(
        item for item in resolved_programs() if item.program_id == "songliang-aid"
    )
    parent = _scholarship(
        "songliang-aid",
        "申請助學金",
        "https://www.slceas.org.tw/index.php/scholarship",
    )
    rules = _scholarship(
        "songliang-aid",
        "助學金實施辦法",
        "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
    )
    pdf = _scholarship(
        "songliang-aid",
        "社團法人台灣松樑教育公益促進協會助學金實施辦法",
        "https://www.slceas.org.tw/images/news/scholarship/20251116_01.pdf",
    )

    assert _is_replaced_navigation_candidate(parent, source) is True
    assert _is_replaced_navigation_candidate(rules, source) is False
    assert _is_replaced_navigation_candidate(pdf, source) is False
