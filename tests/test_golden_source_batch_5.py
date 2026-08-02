# -*- coding: utf-8 -*-

import pytest

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_NOT_REQUIRED
from src.evaluators.eligibility_evaluator import INELIGIBLE, EligibilityEvaluator
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
        "dapeng-aid",
        "115年第1次大鵬科技慈善基金會獎助學金",
        "申請人須具中華民國國籍且未滿25歲，為教育部認可之高中職、五專或大學在學生，"
        "不含軍警校、空中大學、大學在職專班及研究所。家庭狀況須符合低收入戶、"
        "中低收入戶、特殊境遇家庭、主要生計者失業或重大變故等任一項。",
        INELIGIBLE,
    ),
    (
        "hndasset-wenxiang",
        "115年度文向大學優秀在學生獎學金",
        "申請資格為學士班在學生，但不含五專、二專、研究所、空中大學、軍警學校、"
        "在職班、進修部、產訓班、假日班、學分班及公費生。申請人須設籍彰化縣永靖鄉。"
        "低收入戶證明只供申請自強生獎學金者，一般生非必要。",
        INELIGIBLE,
    ),
    (
        "cy-arch-aid",
        "昌益事業獎助學金",
        "申請資格限國內公私立高中職、大專院校日間部學生，且須具低收入戶或"
        "中低收入戶證明。",
        INELIGIBLE,
    ),
    (
        "lihpao-fullon",
        "麗寶福容獎助學金",
        "申請對象限設籍新北市淡水區之在學學生，並須為身心障礙家庭或經濟弱勢家庭學生。",
        INELIGIBLE,
    ),
    (
        "auden-innovation-research",
        "2025耀登炳南創新研究獎",
        "申請對象限國內大專校院資通訊、衛星通訊、智慧能源或環境永續相關系所之"
        "碩士班及博士班在學研究生。",
        INELIGIBLE,
    ),
    (
        "harmony-stability",
        "114年和諧安定獎學金",
        "申請資格為國內公私立大學校院及研究所在學學生，但不含大一新生、夜間部、"
        "進修部、推廣教育、空中大學及延修生。清寒或經濟弱勢學生優先考量。",
        INELIGIBLE,
    ),
    (
        "taishin-youth-volunteer",
        "第27屆台新青少年志工菁英獎",
        "參選資格為熱心參與公益服務，且目前就讀國內立案國中、高中職、五專一至三年級"
        "或同階段實驗教育學校之在學學生。",
        INELIGIBLE,
    ),
)


@pytest.mark.parametrize(
    ("program_id", "title", "body", "expected_status"),
    GOLDEN_CASES,
)
def test_manual_source_batch_5_golden_eligibility(
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