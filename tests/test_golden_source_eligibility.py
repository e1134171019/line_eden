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


# 使用已確認沒有經濟弱勢或其他特殊身分的目前學生背景。
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
        "auden-university-talent",
        "2026耀登炳南大專院校優秀人才獎學金",
        "申請對象：具有中華民國國籍或外籍人士在台灣學校就讀者。"
        "就讀國內已立案大專院校資通訊、生醫工程及環境永續相關系所之"
        "學士班、碩士班及博士班在學學生，不含學士班一年級新生、休學生、"
        "延畢生、學分班及空中大學學生。學士班平均85分以上且系所排名前10%，"
        "無不及格科目，操行80分以上。",
        ELIGIBLE,
    ),
    (
        "cfh-university",
        "鄭豐喜研究所暨大學獎學金",
        "申請對象限國內研究所或大學在學之身心障礙學生。",
        INELIGIBLE,
    ),
    (
        "avc-talented-student",
        "奇鋐教育基金會資優學生獎學金",
        "申請對象限國小高年級、國中及高中資優學生，須由學校推薦。",
        INELIGIBLE,
    ),
    (
        "songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "申請對象為國內大專院校電子、電機相關科系學生，不含夜間部、"
        "推廣教育部、進修部及空中大學；家庭年所得60萬元以下且確有清寒"
        "或家庭變故事實。",
        INELIGIBLE,
    ),
    (
        "sunshine-scholarship",
        "陽光獎助學金",
        "申請對象須為燒燙傷或顱顏患者，或陽光傷友子女。",
        INELIGIBLE,
    ),
    (
        "tf4dr-aid",
        "賑災基金會助學金",
        "申請對象須為申請日前三年內重大天然災害受災家庭子女，並具低收入戶"
        "或中低收入戶身分。",
        INELIGIBLE,
    ),
    (
        "lijin-taoyuan",
        "利晉基金會清寒獎助學金",
        "申請資格限家境清寒學生。",
        INELIGIBLE,
    ),
    (
        "cht-fang-hsien-chi",
        "中華電信方賢齊先生獎學金",
        "全國公私立大專院校在學生，各學院各科系均可申請；低收入戶學生"
        "優先考量，學業優秀者亦可提出申請。",
        ELIGIBLE,
    ),
    (
        "heart-child",
        "心臟病童獎勵學金",
        "申請對象為曾於本基金會合約醫院接受心臟導管或外科手術治療的"
        "心臟病童。",
        INELIGIBLE,
    ),
    (
        "gfc-scholarship",
        "崇友實業獎學金",
        "日間部或進修部電子、電機相關科系學生均可申請；申請者須符合低收入戶、"
        "中低收入戶、清寒或家庭經濟失依其中一項。",
        INELIGIBLE,
    ),
)


@pytest.mark.parametrize(
    ("program_id", "title", "body", "expected_status"),
    GOLDEN_CASES,
)
def test_manual_source_golden_eligibility(
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
    )