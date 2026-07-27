# -*- coding: utf-8 -*-

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


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

    # 建立不含可逆個資內容的設定指紋。
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    return StudentProfile(
        school=str(data["school"]).strip(),
        degree_level=str(data["degree_level"]).strip(),
        program_type=str(data["program_type"]).strip(),
        department=str(data["department"]).strip(),
        year=int(data["year"]),
        employed=bool(data.get("employed", False)),
        average_grade=float(data.get("average_grade", 0)),
        conduct_grade=float(data.get("conduct_grade", 0)),
        class_rank=int(data.get("class_rank", 0)),
        class_size=int(data.get("class_size", 0)),
        residence=str(data.get("residence", "")).strip(),
        special_statuses=tuple(str(item).strip() for item in data.get("special_statuses", [])),
        research_keywords=tuple(str(item).strip() for item in data.get("research_keywords", [])),
    )
