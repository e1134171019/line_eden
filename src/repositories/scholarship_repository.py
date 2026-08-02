# -*- coding: utf-8 -*-

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship

SCHEMA_COLUMNS = {
    "category": "TEXT NOT NULL DEFAULT 'other'",
    "program_id": "TEXT NOT NULL DEFAULT ''",
    "entry_url": "TEXT NOT NULL DEFAULT ''",
    "detail_url": "TEXT NOT NULL DEFAULT ''",
    "match_method": "TEXT NOT NULL DEFAULT ''",
    "match_score": "INTEGER NOT NULL DEFAULT 0",
    "matched_alias": "TEXT NOT NULL DEFAULT ''",
    "detail_evidence_score": "INTEGER NOT NULL DEFAULT 0",
    "resolution_status": "TEXT NOT NULL DEFAULT ''",
    "notice_kind": "TEXT NOT NULL DEFAULT 'unknown'",
    "application_status": "TEXT NOT NULL DEFAULT 'not_applicable'",
    "discovered_at": "TEXT",
    "baseline_at": "TEXT",
    "notified_at": "TEXT",
    "eligibility_status": "TEXT",
    "eligibility_reason": "TEXT",
    "hard_eligibility_status": "TEXT NOT NULL DEFAULT ''",
    "hard_eligibility_reason": "TEXT NOT NULL DEFAULT ''",
    "action_status": "TEXT NOT NULL DEFAULT ''",
    "manual_checks": "TEXT NOT NULL DEFAULT '[]'",
    "review_kind": "TEXT NOT NULL DEFAULT ''",
    "exclusion_reason": "TEXT NOT NULL DEFAULT ''",
    "profile_hash": "TEXT",
    "evaluated_at": "TEXT",
}

NOTIFIABLE_APPLICATION_STATUSES = (
    "open",
    "upcoming",
    "deadline_unknown",
    "evergreen",
)


class ScholarshipRepository:
    """Scholarship 的 SQLite 存取層。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()
        self._migrate_schema()

    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            published_date TEXT NOT NULL,
            source_url TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            program_id TEXT NOT NULL DEFAULT '',
            entry_url TEXT NOT NULL DEFAULT '',
            detail_url TEXT NOT NULL DEFAULT '',
            match_method TEXT NOT NULL DEFAULT '',
            match_score INTEGER NOT NULL DEFAULT 0,
            matched_alias TEXT NOT NULL DEFAULT '',
            detail_evidence_score INTEGER NOT NULL DEFAULT 0,
            resolution_status TEXT NOT NULL DEFAULT '',
            notice_kind TEXT NOT NULL DEFAULT 'unknown',
            application_status TEXT NOT NULL DEFAULT 'not_applicable',
            content_hash TEXT NOT NULL UNIQUE,
            discovered_at TEXT NOT NULL,
            baseline_at TEXT,
            notified_at TEXT,
            eligibility_status TEXT,
            eligibility_reason TEXT,
            hard_eligibility_status TEXT NOT NULL DEFAULT '',
            hard_eligibility_reason TEXT NOT NULL DEFAULT '',
            action_status TEXT NOT NULL DEFAULT '',
            manual_checks TEXT NOT NULL DEFAULT '[]',
            review_kind TEXT NOT NULL DEFAULT '',
            exclusion_reason TEXT NOT NULL DEFAULT '',
            profile_hash TEXT,
            evaluated_at TEXT
        )
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query)
            conn.commit()

    def _migrate_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            existing = self._column_names(conn)
            for name, definition in SCHEMA_COLUMNS.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE scholarships ADD COLUMN {name} {definition}")
            self._fill_discovered_at(conn)
            self._fill_source_urls(conn)
            self._backfill_eligibility_axes(conn)
            conn.commit()

    def _column_names(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(scholarships)").fetchall()
        return {row[1] for row in rows}

    def _fill_discovered_at(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE scholarships SET discovered_at = ? WHERE discovered_at IS NULL",
            [self._now_iso()],
        )

    def _fill_source_urls(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE scholarships SET entry_url = source_url "
            "WHERE entry_url IS NULL OR entry_url = ''"
        )
        conn.execute(
            "UPDATE scholarships SET detail_url = source_url "
            "WHERE detail_url IS NULL OR detail_url = ''"
        )

    def _backfill_eligibility_axes(self, conn: sqlite3.Connection) -> None:
        # 舊版 source_incomplete 曾覆寫硬性資格，必須清除 profile 讓它重跑。
        conn.execute(
            """
            UPDATE scholarships
            SET profile_hash = NULL, evaluated_at = NULL,
                hard_eligibility_status = '', hard_eligibility_reason = '',
                action_status = ''
            WHERE review_kind = 'source_incomplete'
            """
        )
        conn.execute(
            """
            UPDATE scholarships
            SET hard_eligibility_status = COALESCE(eligibility_status, ''),
                hard_eligibility_reason = COALESCE(eligibility_reason, '')
            WHERE hard_eligibility_status = ''
              AND COALESCE(review_kind, '') != 'source_incomplete'
            """
        )
        conn.execute(
            """
            UPDATE scholarships
            SET action_status = CASE
                WHEN notice_kind != 'application'
                  OR application_status IN ('expired', 'stale_unknown', 'not_applicable')
                    THEN 'not_actionable'
                WHEN hard_eligibility_status = 'ineligible' THEN 'reject'
                WHEN hard_eligibility_status = 'eligible'
                  AND resolution_status = 'valid_application_detail'
                    THEN 'apply_candidate'
                WHEN hard_eligibility_status IN ('eligible', 'review')
                  AND resolution_status != 'valid_application_detail'
                    THEN 'verify_source'
                WHEN hard_eligibility_status = 'review' THEN 'manual_review'
                ELSE ''
            END
            WHERE action_status = '' AND hard_eligibility_status != ''
            """
        )

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def is_empty(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(1) FROM scholarships").fetchone()
        return bool(row and row[0] == 0)

    def get_existing_hashes(self, content_hashes: list[str]) -> set[str]:
        if not content_hashes:
            return set()
        placeholders = ",".join(["?"] * len(content_hashes))
        query = f"SELECT content_hash FROM scholarships WHERE content_hash IN ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, content_hashes).fetchall()
        return {row[0] for row in rows}

    def discover(self, scholarships: list[Scholarship]) -> int:
        if not scholarships:
            return 0
        rows = [self._discovery_row(item) for item in scholarships]
        query = """
        INSERT OR IGNORE INTO scholarships (
            source, title, published_date, source_url, category,
            program_id, entry_url, detail_url, match_method, match_score,
            matched_alias, detail_evidence_score, resolution_status,
            notice_kind, application_status, content_hash, discovered_at,
            exclusion_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.executemany(query, rows)
            conn.commit()
        return max(cursor.rowcount, 0)

    def _discovery_row(self, item: Scholarship) -> tuple[object, ...]:
        return (
            item.source,
            item.title,
            item.published_date,
            item.source_url,
            item.category,
            item.program_id,
            item.entry_url or item.source_url,
            item.detail_url or item.source_url,
            item.match_method,
            item.match_score,
            item.matched_alias,
            item.detail_evidence_score,
            item.resolution_status,
            item.notice_kind,
            item.application_status,
            item.content_hash,
            self._now_iso(),
            item.exclusion_reason,
        )

    def list_pending(self) -> list[Scholarship]:
        query = self._select_query("notified_at IS NULL AND baseline_at IS NULL")
        return self._query_scholarships(query, [])

    def list_for_evaluation(self, profile_hash: str) -> list[Scholarship]:
        condition = (
            "notified_at IS NULL AND baseline_at IS NULL "
            "AND (eligibility_status IS NULL OR profile_hash IS NULL OR profile_hash != ? "
            "OR hard_eligibility_status = '' OR action_status = '')"
        )
        return self._query_scholarships(self._select_query(condition), [profile_hash])

    def list_notifiable(
        self,
        profile_hash: str,
        include_review: bool,
    ) -> list[Scholarship]:
        statuses = ["eligible", "review"] if include_review else ["eligible"]
        eligibility_placeholders = ",".join(["?"] * len(statuses))
        period_placeholders = ",".join(["?"] * len(NOTIFIABLE_APPLICATION_STATUSES))
        condition = (
            "notified_at IS NULL AND baseline_at IS NULL AND profile_hash = ? "
            "AND notice_kind = 'application' "
            f"AND application_status IN ({period_placeholders}) "
            f"AND hard_eligibility_status IN ({eligibility_placeholders}) "
            "AND action_status IN ('apply_candidate', 'verify_source', 'manual_review')"
        )
        params = [profile_hash, *NOTIFIABLE_APPLICATION_STATUSES, *statuses]
        return self._query_scholarships(self._select_query(condition), params)

    def _select_query(self, condition: str) -> str:
        return f"""
        SELECT source, title, published_date, source_url, category, content_hash,
               COALESCE(program_id, ''), COALESCE(entry_url, source_url),
               COALESCE(detail_url, source_url), COALESCE(match_method, ''),
               COALESCE(match_score, 0), COALESCE(matched_alias, ''),
               COALESCE(detail_evidence_score, 0), COALESCE(resolution_status, ''),
               COALESCE(notice_kind, 'unknown'),
               COALESCE(application_status, 'not_applicable'),
               COALESCE(eligibility_status, ''), COALESCE(eligibility_reason, ''),
               COALESCE(hard_eligibility_status, ''),
               COALESCE(hard_eligibility_reason, ''), COALESCE(action_status, ''),
               COALESCE(manual_checks, '[]'), COALESCE(review_kind, ''),
               COALESCE(exclusion_reason, '')
        FROM scholarships
        WHERE {condition}
        ORDER BY published_date DESC, id DESC
        """

    def _query_scholarships(
        self,
        query: str,
        params: list[str],
    ) -> list[Scholarship]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._to_scholarship(row) for row in rows]

    def _to_scholarship(self, row: tuple[object, ...]) -> Scholarship:
        return Scholarship(
            source=str(row[0]),
            title=str(row[1]),
            published_date=str(row[2]),
            source_url=str(row[3]),
            category=str(row[4]),
            content_hash=str(row[5]),
            program_id=str(row[6]),
            entry_url=str(row[7]),
            detail_url=str(row[8]),
            match_method=str(row[9]),
            match_score=int(row[10]),
            matched_alias=str(row[11]),
            detail_evidence_score=int(row[12]),
            resolution_status=str(row[13]),
            notice_kind=str(row[14]),
            application_status=str(row[15]),
            eligibility_status=str(row[16]),
            eligibility_reason=str(row[17]),
            hard_eligibility_status=str(row[18]),
            hard_eligibility_reason=str(row[19]),
            action_status=str(row[20]),
            manual_checks=_decode_manual_checks(str(row[21])),
            review_kind=str(row[22]),
            exclusion_reason=str(row[23]),
        )

    def mark_eligibility(
        self,
        content_hash: str,
        status: str,
        reason: str,
        profile_hash: str,
        notice_kind: str = "application",
        application_status: str = "deadline_unknown",
        exclusion_reason: str = "",
        manual_checks: tuple[str, ...] = tuple(),
        review_kind: str = "",
        detail_evidence_score: int = 0,
        resolution_status: str = "",
        hard_eligibility_status: str = "",
        hard_eligibility_reason: str = "",
        action_status: str = "",
    ) -> int:
        hard_status = hard_eligibility_status or status
        hard_reason = hard_eligibility_reason or reason
        query = """
        UPDATE scholarships
        SET notice_kind = ?, application_status = ?, eligibility_status = ?,
            eligibility_reason = ?, hard_eligibility_status = ?,
            hard_eligibility_reason = ?, action_status = ?, manual_checks = ?,
            review_kind = ?, detail_evidence_score = ?, resolution_status = ?,
            exclusion_reason = ?, profile_hash = ?, evaluated_at = ?
        WHERE content_hash = ? AND notified_at IS NULL AND baseline_at IS NULL
        """
        params = [
            notice_kind,
            application_status,
            hard_status,
            hard_reason,
            hard_status,
            hard_reason,
            action_status,
            _encode_manual_checks(manual_checks),
            review_kind,
            max(detail_evidence_score, 0),
            resolution_status,
            exclusion_reason,
            profile_hash,
            self._now_iso(),
            content_hash,
        ]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            conn.commit()
        return max(cursor.rowcount, 0)

    def count_eligibility(self, profile_hash: str, status: str) -> int:
        query = """
        SELECT COUNT(1) FROM scholarships
        WHERE profile_hash = ? AND hard_eligibility_status = ?
          AND notified_at IS NULL AND baseline_at IS NULL
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(query, [profile_hash, status]).fetchone()
        return int(row[0]) if row else 0

    def mark_baseline(self, content_hashes: list[str]) -> int:
        return self._mark_time("baseline_at", content_hashes)

    def mark_notified(self, content_hashes: list[str]) -> int:
        return self._mark_time("notified_at", content_hashes)

    def _mark_time(self, column: str, content_hashes: list[str]) -> int:
        if not content_hashes:
            return 0
        placeholders = ",".join(["?"] * len(content_hashes))
        query = (
            f"UPDATE scholarships SET {column} = ? "
            f"WHERE content_hash IN ({placeholders}) AND {column} IS NULL"
        )
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, [self._now_iso(), *content_hashes])
            conn.commit()
        return max(cursor.rowcount, 0)


def _encode_manual_checks(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _decode_manual_checks(value: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return tuple()
    if not isinstance(decoded, list):
        return tuple()
    return tuple(str(item) for item in decoded if str(item).strip())
