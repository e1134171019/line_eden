# -*- coding: utf-8 -*-

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from config import ELIGIBILITY_RULE_VERSION
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository


# 建立固定學生背景。
def _profile() -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="",
        special_statuses=tuple(),
        research_keywords=("電力電子",),
    )


# 本次語意修正必須提升版本，迫使雲端 SQLite 重新評估既有公告。
def test_current_rule_version_is_v14() -> None:
    assert ELIGIBILITY_RULE_VERSION == "eligibility-v14"


# 舊版只含 profile 的雜湊不得等於目前包含規則版本的雜湊。
def test_profile_fingerprint_includes_rule_version() -> None:
    profile = _profile()
    legacy_payload = json.dumps(asdict(profile), ensure_ascii=False, sort_keys=True)
    legacy_hash = hashlib.sha256(legacy_payload.encode("utf-8")).hexdigest()

    assert ELIGIBILITY_RULE_VERSION
    assert profile.fingerprint() != legacy_hash


# 資料庫保存舊版指紋後，正式流程仍會把公告列入重新評估。
def test_old_rule_fingerprint_forces_reevaluation(tmp_path: Path) -> None:
    profile = _profile()
    item = Scholarship.from_raw(
        "lhu",
        "測試獎學金",
        "2026-07-28",
        "https://example.com/scholarship",
    )
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    repository.discover([item])
    repository.mark_eligibility(
        item.content_hash,
        "eligible",
        "舊版判定",
        "legacy-profile-only-hash",
    )

    pending = repository.list_for_evaluation(profile.fingerprint())

    assert [candidate.content_hash for candidate in pending] == [item.content_hash]
