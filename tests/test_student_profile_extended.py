# -*- coding: utf-8 -*-

import json
from pathlib import Path

from src.profiles.student_profile import load_student_profile


# 新 profile 應完整保留已確認的真實學生條件。
def test_load_extended_student_profile(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "school": "龍華科技大學",
                "degree_level": "學士",
                "program_type": "進修部四技",
                "department": "電子工程系",
                "year": 2,
                "employed": True,
                "latest_semester_average": 90.60,
                "latest_conduct_grade": 86,
                "latest_class_rank": 1,
                "latest_class_size": 17,
                "residence": "新北市新莊區",
                "special_statuses": [],
                "research_keywords": ["電力電子", "能源"],
                "nationality": "中華民國",
                "enrollment_status": "在學、未休學",
                "credits_earned": 67,
                "residence_years": 10,
                "cumulative_average": 88.03,
                "academic_year_average": 90.34,
                "has_failed_courses": False,
                "has_major_discipline": False,
                "household_income": None,
                "has_received_similar_scholarship": None,
                "can_obtain_recommendation": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    profile = load_student_profile(profile_path)

    assert profile.average_grade == 90.60
    assert profile.conduct_grade == 86
    assert profile.class_rank == 1
    assert profile.class_size == 17
    assert profile.credits_earned == 67
    assert profile.residence == "新北市新莊區"
    assert profile.residence_years == 10
    assert profile.special_statuses == tuple()
    assert profile.has_failed_courses is False
    assert profile.has_major_discipline is False


# 舊 profile 欄位仍可載入，避免既有 Secret 在部署時立即失敗。
def test_legacy_profile_fields_remain_compatible(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "school": "測試科技大學",
                "degree_level": "學士",
                "program_type": "進修部",
                "department": "電子工程系",
                "year": 2,
                "average_grade": 90.34,
                "conduct_grade": 85,
                "class_rank": 1,
                "class_size": 17,
            }
        ),
        encoding="utf-8",
    )

    profile = load_student_profile(profile_path)

    assert profile.latest_semester_average == 90.34
    assert profile.latest_conduct_grade == 85
    assert profile.latest_class_rank == 1
    assert profile.latest_class_size == 17
    assert profile.has_failed_courses is None
    assert profile.has_major_discipline is None
