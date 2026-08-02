# -*- coding: utf-8 -*-

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from config import ELIGIBILITY_RULE_VERSION


@dataclass(frozen=True)
class StudentProfile:
    """獎學金資格判斷所需的私密學生背景。"""

    school: str
    degree_level: str
    program_type: str
    department: str
    year: int
    employed: bool
    average_grade: float
    conduct_grade: float
    class_rank: int
    class_size: int
    residence: str
    special_statuses: tuple[str, ...]
    research_keywords: tuple[str, ...]
    nationality: str = ""
    enrollment_status: str = ""
    credits_earned: int = 0
    residence_years: float = 0.0
    cumulative_average: float = 0.0
    academic_year_average: float = 0.0
    latest_semester_average: float = 0.0
    latest_conduct_grade: float = 0.0
    latest_class_rank: int = 0
    latest_class_size: int = 0
    has_failed_courses: bool | None = None
    has_major_discipline: bool | None = None
    household_income: float | None = None
    household_size: int = 0
    has_received_similar_scholarship: bool | None = None
    can_obtain_recommendation: bool | None = None
    special_statuses_confirmed: bool = False

    # 將背景與資格規則版本共同轉成不可逆指紋，規則更新後會自動重算。
    def fingerprint(self) -> str:
        payload = {
            "eligibility_rule_version": ELIGIBILITY_RULE_VERSION,
            "profile": asdict(self),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# 從私密 JSON 檔案載入並驗證學生背景。
def load_student_profile(profile_path: Path) -> StudentProfile:
    if not profile_path.exists():
        raise RuntimeError(
            "找不到 profile.json；請由 profile.example.json 建立本機私密設定。"
        )
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return _build_profile(data)


# 將 JSON 字典轉為型別明確的 StudentProfile。
def _build_profile(data: dict[str, Any]) -> StudentProfile:
    required = ("school", "degree_level", "program_type", "department", "year")
    missing = [name for name in required if not data.get(name)]
    if missing:
        raise RuntimeError(f"profile.json 缺少必要欄位：{', '.join(missing)}")
    latest_average = _float_value(
        data,
        "latest_semester_average",
        fallback="average_grade",
    )
    latest_conduct = _float_value(
        data,
        "latest_conduct_grade",
        fallback="conduct_grade",
    )
    latest_rank = _int_value(data, "latest_class_rank", fallback="class_rank")
    latest_size = _int_value(data, "latest_class_size", fallback="class_size")
    return StudentProfile(
        school=str(data["school"]).strip(),
        degree_level=str(data["degree_level"]).strip(),
        program_type=str(data["program_type"]).strip(),
        department=str(data["department"]).strip(),
        year=int(data["year"]),
        employed=bool(data.get("employed", False)),
        average_grade=latest_average,
        conduct_grade=latest_conduct,
        class_rank=latest_rank,
        class_size=latest_size,
        residence=str(data.get("residence", "")).strip(),
        special_statuses=tuple(
            str(item).strip() for item in data.get("special_statuses", [])
        ),
        research_keywords=tuple(
            str(item).strip() for item in data.get("research_keywords", [])
        ),
        nationality=str(data.get("nationality", "")).strip(),
        enrollment_status=str(data.get("enrollment_status", "")).strip(),
        credits_earned=int(data.get("credits_earned", 0)),
        residence_years=float(data.get("residence_years", 0)),
        cumulative_average=float(data.get("cumulative_average", 0)),
        academic_year_average=float(data.get("academic_year_average", 0)),
        latest_semester_average=latest_average,
        latest_conduct_grade=latest_conduct,
        latest_class_rank=latest_rank,
        latest_class_size=latest_size,
        has_failed_courses=_optional_bool(data, "has_failed_courses"),
        has_major_discipline=_optional_bool(data, "has_major_discipline"),
        household_income=_optional_float(data, "household_income"),
        household_size=int(data.get("household_size", 0)),
        has_received_similar_scholarship=_optional_bool(
            data,
            "has_received_similar_scholarship",
        ),
        can_obtain_recommendation=_optional_bool(
            data,
            "can_obtain_recommendation",
        ),
        special_statuses_confirmed="special_statuses" in data,
    )


# 新欄位優先，未提供時沿用舊 profile 欄位。
def _float_value(data: dict[str, Any], name: str, *, fallback: str) -> float:
    value = data.get(name, data.get(fallback, 0))
    return float(value or 0)


# 新欄位優先，未提供時沿用舊 profile 欄位。
def _int_value(data: dict[str, Any], name: str, *, fallback: str) -> int:
    value = data.get(name, data.get(fallback, 0))
    return int(value or 0)


# 缺少欄位代表未知；JSON true／false 才代表已確認事實。
def _optional_bool(data: dict[str, Any], name: str) -> bool | None:
    if name not in data or data[name] is None:
        return None
    if not isinstance(data[name], bool):
        raise RuntimeError(f"profile.json 的 {name} 必須是 true、false 或 null")
    return data[name]


# 金額缺少時保留未知，不以 0 元代替。
def _optional_float(data: dict[str, Any], name: str) -> float | None:
    if name not in data or data[name] is None:
        return None
    return float(data[name])