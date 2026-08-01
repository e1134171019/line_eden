# -*- coding: utf-8 -*-

from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import (
    REVISION_CHANGED,
    REVISION_INITIALIZED,
    REVISION_UNCHANGED,
    ScholarshipRepository,
)


def _item() -> Scholarship:
    return Scholarship.from_raw(
        "source",
        "能源獎學金",
        "2026-08-01",
        "https://example.test/list?id=88",
        detail_url="https://example.test/detail/88?utm_source=line",
    )


def test_announcement_id_is_persisted_and_round_tripped(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "scholarships.db")
    item = _item()

    repo.discover([item])
    stored = repo.list_by_hashes([item.content_hash])

    assert stored[0].announcement_id == item.announcement_id
    assert stored[0].announcement_id


def test_first_revision_initializes_without_reopening_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "scholarships.db"
    repo = ScholarshipRepository(db_path)
    item = _item()
    repo.discover([item])
    repo.mark_eligibility(item.content_hash, "eligible", "硬性符合", "profile-a")
    repo.mark_notified([item.content_hash])

    status = repo.register_revision(item.content_hash, "revision-a")

    assert status == REVISION_INITIALIZED
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT notified_at, eligibility_status, revision_hash FROM scholarships "
            "WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] == "eligible"
    assert row[2] == "revision-a"


def test_same_revision_keeps_existing_notification_state(tmp_path: Path) -> None:
    db_path = tmp_path / "scholarships.db"
    repo = ScholarshipRepository(db_path)
    item = _item()
    repo.discover([item])
    repo.register_revision(item.content_hash, "revision-a")
    repo.mark_eligibility(item.content_hash, "eligible", "硬性符合", "profile-a")
    repo.mark_notified([item.content_hash])

    status = repo.register_revision(item.content_hash, "revision-a")

    assert status == REVISION_UNCHANGED
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT notified_at, eligibility_status FROM scholarships WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] == "eligible"


def test_changed_revision_reopens_evaluation_and_notification(tmp_path: Path) -> None:
    db_path = tmp_path / "scholarships.db"
    repo = ScholarshipRepository(db_path)
    item = _item()
    repo.discover([item])
    repo.register_revision(item.content_hash, "revision-a")
    repo.mark_eligibility(item.content_hash, "eligible", "硬性符合", "profile-a")
    repo.mark_notified([item.content_hash])

    status = repo.register_revision(item.content_hash, "revision-b")

    assert status == REVISION_CHANGED
    assert repo.needs_evaluation(item.content_hash, "profile-a") is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT notified_at, eligibility_status, revision_hash FROM scholarships "
            "WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert row == (None, None, "revision-b")
