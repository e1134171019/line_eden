# -*- coding: utf-8 -*-

from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship
from src.repositories.announcement_revision_repository import (
    REVISION_BASELINED,
    REVISION_CHANGED,
    REVISION_UNCHANGED,
    AnnouncementRevisionRepository,
)
from src.repositories.scholarship_repository import ScholarshipRepository


def _stored_item(repository: ScholarshipRepository) -> Scholarship:
    item = Scholarship.from_raw(
        "test",
        "能源獎學金",
        "2026-08-01",
        "https://example.test/detail",
    )
    repository.discover([item])
    repository.mark_eligibility(
        item.content_hash,
        "eligible",
        "硬性條件符合。",
        "profile-v1",
        "application",
        "open",
        resolution_status="valid_application_detail",
    )
    repository.mark_notified([item.content_hash])
    return item


def test_first_revision_is_baseline_and_unchanged_does_not_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    repository = ScholarshipRepository(db_path)
    item = _stored_item(repository)
    revisions = AnnouncementRevisionRepository(db_path)

    first = revisions.observe(item.content_hash, "announcement-1", "revision-a")
    same = revisions.observe(item.content_hash, "announcement-1", "revision-a")

    assert first.status == REVISION_BASELINED
    assert same.status == REVISION_UNCHANGED
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT notified_at, hard_eligibility_status FROM scholarships "
            "WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] == "eligible"


def test_changed_revision_reopens_evaluation_and_notification(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    repository = ScholarshipRepository(db_path)
    item = _stored_item(repository)
    revisions = AnnouncementRevisionRepository(db_path)
    revisions.observe(item.content_hash, "announcement-1", "revision-a")

    changed = revisions.observe(item.content_hash, "announcement-1", "revision-b")

    assert changed.status == REVISION_CHANGED
    assert changed.previous_hash == "revision-a"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT notified_at, baseline_at, profile_hash,
                   hard_eligibility_status, action_status
            FROM scholarships WHERE content_hash = ?
            """,
            [item.content_hash],
        ).fetchone()
    assert row == (None, None, None, "", "")
    pending = repository.list_for_evaluation("profile-v1")
    assert [value.content_hash for value in pending] == [item.content_hash]
