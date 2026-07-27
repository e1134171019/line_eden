# -*- coding: utf-8 -*-

import json
from pathlib import Path

import pytest

from src.profiles.student_profile import load_student_profile


# 建立完整測試背景資料。
def _profile_data() -> dict[str, object]:
    return {
        "school": "測試科技大學",
        "degree_level": "學士",
        "program_type": "進修部",
        "department": "電子工程系",
        "year": 2,
        "employed": True,
        "average_grade": 90.34,
        "conduct_grade": 85,
        "class_rank": 1,
        "class_size": 17,
        "residence": "新北市",
        "special_statuses": [],
        "research_keywords": ["逆變器", "電力電子"],
    }


# 驗證私密 JSON 可以載入並產生穩定指紋。
def test_load_profile_and_fingerprint(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(_profile_data(), ensure_ascii=False),
        encoding="utf-8",
    )

    first = load_student_profile(profile_path)
    second = load_student_profile(profile_path)

    assert first.department == "電子工程系"
    assert first.fingerprint() == second.fingerprint()


# 驗證找不到私密背景時採失敗關閉，不允許直接推播。
def test_missing_profile_raises_runtime_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="profile.json"):
        load_student_profile(tmp_path / "profile.json")


# 驗證缺少必要欄位時拒絕啟動個人化判斷。
def test_profile_requires_core_fields(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="缺少必要欄位"):
        load_student_profile(profile_path)
