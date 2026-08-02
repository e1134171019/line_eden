# -*- coding: utf-8 -*-

import pytest

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_NOT_REQUIRED
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    EligibilityEvaluator,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 使用已確認無特殊身分、目前為大二進修部電子工程學生的背景。
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
        research_keywords=("電子", "電機", "電力", "能源"),
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


# 建立不含期限判斷的人工核對公告。
def _scholarship(program_id: str, title: str) -> Scholarship:
    return Scholarship.from_raw(
        source=f"golden-{program_id}",
        title=title,
        published_date="",
        source_url=f"https://example.test/{program_id}",
        program_id=program_id,
        entry_url=f"https://example.test/{program_id}",
        detail_url=f"https://example.test/{program_id}/detail",
    )


GOLDEN_CASES = (
    (
        "yonglin-hope",
        "永齡銘日希望獎助學金",
        "申請資格：凡具備永齡希望小學就學經歷，現為國內大專院校在學學生，"
        "且前一學年學業成績平均75分以上者得提出申請。",
        INELIGIBLE,
    ),
    (
        "ht-emergency",
        "行天宮學生急難濟助",
        "濟助對象：因家庭經濟突逢變故而影響就學中之國小、國中、高中職及"
        "大專院校學生。大學部公費生、研究生及休學或輟學者不列入濟助對象。"
        "學生案件須由學校初核並加蓋學校關防後提出。",
        INELIGIBLE,
    ),
    (
        "ht-talented-long-term",
        "行天宮資優學生長期獎助",
        "培育對象為具中華民國國籍，國內經政府立案之公私立大學校院大二含以上"
        "及碩博士班在學生。大學部每學期成績均達80分以上、系排名前10%以內、"
        "操行80分以上。家境經濟缺乏或困難之就學學生優先錄取。",
        ELIGIBLE,
    ),
    (
        "ht-student-aid",
        "行天宮助學金",
        "助學對象為國內公私立大專學校在學學生，因家庭經濟缺乏或變故致就學困難者。"
        "年滿25歲含以上者、研究所以上、延修、軍警校、推廣教育、空中大學或"
        "在職進修學生皆不列入本辦法之助學對象。",
        INELIGIBLE,
    ),
    (
        "sunshine-wanzu",
        "萬足燒傷勞工子女大專生獎助學金",
        "申請資格：父母任一方為重大燒傷且須為勞工身分；申請人須為國內大專院校"
        "在學學生，前一學年學業成績平均70分以上。",
        INELIGIBLE,
    ),
    (
        "cfh-disabled-family",
        "鄭豐喜肢障者家庭子女獎學金",
        "申請資格：肢障者家庭子女，係指父母或法定監護人領有身心障礙證明，"
        "障別為肢障且程度為中度、重度或極重度之家庭子女。",
        INELIGIBLE,
    ),
    (
        "lovepeace-disadvantaged",
        "祥和文教基金會優秀清寒獎學金",
        "申請對象：設籍臺中市之清寒優秀學生。大學生含二技、四技之上、下學期"
        "學業成績平均85分以上，操行80分以上。",
        INELIGIBLE,
    ),
)


@pytest.mark.parametrize(
    ("program_id", "title", "body", "expected_status"),
    GOLDEN_CASES,
)
def test_manual_source_batch_4_golden_eligibility(
    program_id: str,
    title: str,
    body: str,
    expected_status: str,
) -> None:
    decision = EligibilityEvaluator().evaluate(
        _scholarship(program_id, title),
        body,
        _profile(),
        rules_status=RULES_STATUS_NOT_REQUIRED,
    )

    assert decision.status == expected_status, (
        program_id,
        decision.status,
        decision.reasons,
        decision.manual_checks,
    )