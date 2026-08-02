# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_NOT_REQUIRED
from src.evaluators.eligibility_evaluator import ELIGIBLE, EligibilityEvaluator
from src.evaluators.production_semantic_guards import (
    _term_is_required_without_exclusions,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


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
        research_keywords=("電子", "資通訊", "電機", "電力"),
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


# 排除學士一年級新生後，又說明新生繳交文件，仍不代表方案限定新生。
def test_excluded_freshman_subgroup_is_not_required_group() -> None:
    text = (
        "申請對象：就讀國內大專院校資通訊相關系所之修業年限學士班、碩士班及"
        "博士班在學學生，不含學士班一年級新生、休學生、延畢生。"
        "備註：一年級新生以學士前一學歷之畢業成績為準；"
        "非一年級新生現讀二年級以上者提供上下學期成績單。"
    )

    assert not _term_is_required_without_exclusions(text, "耀登優秀人才獎學金", ("新生", "大一"))


# 真正明文限定大一新生時仍必須判定為必要資格。
def test_explicit_freshman_only_requirement_remains_required() -> None:
    text = "申請資格限大一新生，其他年級不得申請。"

    assert _term_is_required_without_exclusions(text, "新生獎學金", ("新生", "大一"))


# 使用 production 原文片段時，大二學生不得再被反向判成限定新生。
def test_auden_production_text_is_not_rejected_as_freshman_only() -> None:
    scholarship = Scholarship.from_raw(
        source="tun-program-auden-university-talent",
        title="【公告】『2026耀登炳南大專院校優秀人才獎學金』歡迎各界踴躍推薦報名！",
        published_date="2026-07-23",
        source_url="https://www.auden.com.tw/2026scholarship/",
        program_id="auden-university-talent",
        entry_url="https://www.auden.com.tw/news-4/",
        detail_url="https://www.auden.com.tw/2026scholarship/",
    )
    detail = (
        "貳、申請對象。具有中華民國國籍。"
        "就讀國內已立案大專院校資通訊、生醫工程及環境永續相關系所之修業年限"
        "學士班、碩士班及博士班在學學生，不含學士班一年級新生、休學生、"
        "延畢生、學分班及空中大學學生。"
        "學士班學期學科總平均分數85分以上且系所排名前10%。"
        "申請者須無不及格科目，操行成績80分以上。"
        "備註：一年級新生以前一學歷之歷年畢業總成績為準；"
        "非一年級新生現讀二年級以上在學學生，以114學年上下學期總成績為準。"
    )

    decision = EligibilityEvaluator().evaluate(
        scholarship,
        detail,
        _profile(),
        rules_status=RULES_STATUS_NOT_REQUIRED,
    )

    assert decision.status == ELIGIBLE
    assert "公告限定新生或大一學生。" not in decision.reasons
