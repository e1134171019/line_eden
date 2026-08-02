# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

REVISION_BASELINED = "baselined"
REVISION_UNCHANGED = "unchanged"
REVISION_CHANGED = "changed"


@dataclass(frozen=True)
class RevisionObservation:
    """單次 revision 觀察結果。"""

    status: str
    previous_hash: str = ""
    current_hash: str = ""


class AnnouncementRevisionRepository:
    """在同一 SQLite 中保存公告 revision，並原子重開變更公告生命週期。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._create_table()

    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS announcement_revisions (
            content_hash TEXT PRIMARY KEY,
            announcement_id TEXT NOT NULL,
            revision_hash TEXT NOT NULL,
            observed_at TEXT NOT NULL
        )
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query)
            conn.commit()

    def observe(
        self,
        content_hash: str,
        announcement_id: str,
        revision_hash: str,
    ) -> RevisionObservation:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT revision_hash FROM announcement_revisions WHERE content_hash = ?",
                [content_hash],
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO announcement_revisions (
                        content_hash, announcement_id, revision_hash, observed_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [content_hash, announcement_id, revision_hash, now],
                )
                conn.commit()
                return RevisionObservation(REVISION_BASELINED, "", revision_hash)

            previous = str(row[0])
            if previous == revision_hash:
                conn.execute(
                    """
                    UPDATE announcement_revisions
                    SET announcement_id = ?, observed_at = ?
                    WHERE content_hash = ?
                    """,
                    [announcement_id, now, content_hash],
                )
                conn.commit()
                return RevisionObservation(REVISION_UNCHANGED, previous, revision_hash)

            conn.execute(
                """
                UPDATE announcement_revisions
                SET announcement_id = ?, revision_hash = ?, observed_at = ?
                WHERE content_hash = ?
                """,
                [announcement_id, revision_hash, now, content_hash],
            )
            conn.execute(
                """
                UPDATE scholarships
                SET baseline_at = NULL,
                    notified_at = NULL,
                    eligibility_status = NULL,
                    eligibility_reason = NULL,
                    hard_eligibility_status = '',
                    hard_eligibility_reason = '',
                    action_status = '',
                    manual_checks = '[]',
                    review_kind = '',
                    exclusion_reason = '',
                    profile_hash = NULL,
                    evaluated_at = NULL
                WHERE content_hash = ?
                """,
                [content_hash],
            )
            conn.commit()
            return RevisionObservation(REVISION_CHANGED, previous, revision_hash)

    def get_revision_hash(self, content_hash: str) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT revision_hash FROM announcement_revisions WHERE content_hash = ?",
                [content_hash],
            ).fetchone()
        return str(row[0]) if row else ""
