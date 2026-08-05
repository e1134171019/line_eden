# -*- coding: utf-8 -*-

import json
from pathlib import Path

from src.catalogs.tun_2025_program_catalog import TUN_2025_PROGRAMS

GROUND_TRUTH_PATH = Path("artifacts/manual-source-ground-truth-2026-08-02.json")
PRIVATE_PROFILE_KEYS = {
    "school",
    "department",
    "year",
    "average_grade",
    "conduct_grade",
    "class_rank",
    "class_size",
    "nationality",
    "enrollment_status",
    "residence",
    "household_income",
}


def _load_ground_truth() -> dict[str, object]:
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def test_manual_source_ground_truth_has_unique_record_ids() -> None:
    document = _load_ground_truth()
    programs = document["programs"]
    assert isinstance(programs, list)

    record_ids = [item["record_id"] for item in programs]
    assert len(record_ids) == len(set(record_ids))
    assert all(record_ids)


def test_manual_source_ground_truth_uses_only_catalog_program_ids() -> None:
    document = _load_ground_truth()
    programs = document["programs"]
    catalog_ids = {program.program_id for program in TUN_2025_PROGRAMS}

    referenced_ids = {
        item["program_id"]
        for item in programs
        if item.get("program_id") is not None
    }
    assert referenced_ids <= catalog_ids


def test_manual_source_ground_truth_contains_no_private_profile_fields() -> None:
    document = _load_ground_truth()
    serialized = json.dumps(document, ensure_ascii=False)

    assert all(f'"{key}"' not in serialized for key in PRIVATE_PROFILE_KEYS)


def test_manual_source_ground_truth_marks_incomplete_sources_explicitly() -> None:
    document = _load_ground_truth()
    programs = document["programs"]
    incomplete = {
        item["record_id"]
        for item in programs
        if "incomplete" in item["evidence_status"] or item["evidence_status"] == "partial"
    }

    assert "cht-fang-hsien-chi" in incomplete
    assert "lhu-lee-chang-yung-current-relay" in incomplete
