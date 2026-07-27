# -*- coding: utf-8 -*-

import json
from pathlib import Path
from typing import Any

import pytest

from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eligibility_cases.json"
ELIGIBILITY_CASES = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# 建立匿名化的進修部電子工程學生背景。
def _build_profile() -> StudentProfile:
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
        research_keywords=("逆變器", "電力電子", "能源"),
    )


# 建立每個案例使用的公告模型。
def _build_item(title: str, index: int) -> Scholarship:
    return Scholarship.from_raw(
        "fixture",
        title,
        "2026-07-27",
        f"https://example.com/case/{index}",
    )


# 驗證容易誤判的公告句型都有穩定結果與可追蹤原因。
@pytest.mark.parametrize("case", ELIGIBILITY_CASES, ids=lambda case: case["name"])
def test_anonymized_eligibility_cases(case: dict[str, Any]) -> None:
    index = ELIGIBILITY_CASES.index(case)
    decision = EligibilityEvaluator().evaluate(
        _build_item(case["title"], index),
        case["detail"],
        _build_profile(),
    )

    assert decision.status == case["expected"]
    assert case["reason_contains"] in decision.reason_text()
