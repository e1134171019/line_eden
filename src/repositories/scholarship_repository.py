# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship, build_dedup_hash

SCHEMA_COLUMNS = {
    "category": "TEXT NOT NULL DEFAULT 'other'",
    "notice_kind": "TEXT NOT NULL DEFAULT 'unknown'",
    "dedup_hash": "TEXT",
    "discovered_at": "TEXT",
    "baseline_at": "TEXT",
    "notified_at": "TEXT",
    "eligibility_status": "TEXT",
    "eligibility_reason": "TEXT",
    "profile_hash": "TEXT",
    "evaluated_at": "TEXT",
}


class ScholarshipRepository:
    """Scholarship 的 SQLite 存取層。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()
        self._migrate_schema()

    # 只建立資料表；索引必須等舊資料庫完成欄位遷移後再建立。
    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            published_date TEXT NOT NULL,
            source_url TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            notice_kind TEXT NOT NULL DEFAULT 'unknown',
            content_hash TEXT NOT NULL UNIQUE,
            dedup_hash TEXT,
            discovered_at TEXT NOT NULL,
            baseline_at TEXT,
            notified_at TEXT,
            eligibility_status TEXT,
            eligibility_reason TEXT,
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
            self._fill_dedup_hashes(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scholarships_dedup_hash "
                "ON scholarships(dedup_hash)"
            )
            conn.commit()

    def _column_names(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(scholarships)").fetchall()
        return {row[1] for row in rows}

    def _fill_discovered_at(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE scholarships SET discovered_at = ? WHERE discovered_at IS NULL",
            [self._now_iso()],
        )

    def _fill_dedup_hashes(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT id, title FROM scholarships "
            "WHERE dedup_hash IS NULL OR dedup_hash = ''"
        ).fetchall()
        conn.executemany(
            "UPDATE scholarships SET dedup_hash = ? WHERE id = ?",
            [(build_dedup_hash(title), row_id) for row_id, title in rows],
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

    def get_existing_dedup_hashes(self, dedup_hashes: list[str]) -> set[str]:
        values = [value for value in dedup_hashes if value]
        if not values:
            return set()
        placeholders = ",".join(["?"] * len(values))
        query = f"SELECT dedup_hash FROM scholarships WHERE dedup_hash IN ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, values).fetchall()
        return {row[0] for row in rows if row[0]}

    # 同來源 content_hash 與跨來源 dedup_hash 都會被去重。
    def discover(self, scholarships: list[Scholarship]) -> int:
        if not scholarships:
            return 0
        existing = self.get_existing_dedup_hashes([
            item.dedup_hash or build_dedup_hash(item.title) for item in scholarships
        ])
        new_items: list[Scholarship] = []
        seen = set(existing)
        for item in scholarships:
            dedup_hash = item.dedup_hash or build_dedup_hash(item.title)
            if dedup_hash in seen:
                continue
            seen.add(dedup_hash)
            new_items.append(item)
        if not new_items:
            return 0
        rows = [self._discovery_row(item) for item in new_items]
        query = """
        INSERT OR IGNORE INTO scholarships (
            source, title, published_date, source_url, category, notice_kind,
            content_hash, dedup_hash, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.executemany(query, rows)
            conn.commit()
        return max(cursor.rowcount, 0)

    def _discovery_row(self, item: Scholarship) -> tuple[str, ...]:
        return (
            item.source,
            item.title,
            item.published_date,
            item.source_url,
            item.category,
            item.notice_kind,
            item.content_hash,
            item.dedup_hash or build_dedup_hash(item.title),
            self._now_iso(),
        )

    def list_pending(self) -> list[Scholarship]:
        query = self._select_query("notified_at IS NULL AND baseline_at IS NULL")
        return self._query_scholarships(query, [])

    def list_for_evaluation(self, profile_hash: str) -> list[Scholarship]:
        condition = (
            "notified_at IS NULL AND baseline_at IS NULL "
            "AND (eligibility_status IS NULL OR profile_hash IS NULL OR profile_hash != ?)"
        )
        return self._query_scholarships(self._select_query(condition), [profile_hash])

    def list_notifiable(
        self,
        profile_hash: str,
        include_review: bool,
    ) -> list[Scholarship]:
        statuses = ["eligible", "review"] if include_review else ["eligible"]
        placeholders = ",".join(["?"] * len(statuses))
        condition = (
            "notified_at IS NULL AND baseline_at IS NULL AND profile_hash = ? "
            "AND notice_kind = 'application' "
            f"AND eligibility_status IN ({placeholders})"
        )
        params = [profile_hash, *statuses]
        return self._query_scholarships(self._select_query(condition), params)

    def _select_query(self, condition: str) -> str:
        return f"""
        SELECT source, title, published_date, source_url, category, content_hash,
               COALESCE(notice_kind, 'unknown'),
               COALESCE(eligibility_status, ''), COALESCE(eligibility_reason, ''),
               COALESCE(dedup_hash, '')
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

    def _to_scholarship(self, row: tuple[str, ...]) -> Scholarship:
        return Scholarship(
            source=row[0],
            title=row[1],
            published_date=row[2],
            source_url=row[3],
            category=row[4],
            content_hash=row[5],
            notice_kind=row[6],
            eligibility_status=row[7],
            eligibility_reason=row[8],
            dedup_hash=row[9],
        )

    def mark_eligibility(
        self,
        content_hash: str,
        status: str,
        reason: str,
        profile_hash: str,
        notice_kind: str = "application",
    ) -> int:
        query = """
        UPDATE scholarships
        SET notice_kind = ?, eligibility_status = ?, eligibility_reason = ?,
            profile_hash = ?, evaluated_at = ?
        WHERE content_hash = ? AND notified_at IS NULL AND baseline_at IS NULL
        """
        params = [notice_kind, status, reason, profile_hash, self._now_iso(), content_hash]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            conn.commit()
        return max(cursor.rowcount, 0)

    def count_eligibility(self, profile_hash: str, status: str) -> int:
        query = """
        SELECT COUNT(1) FROM scholarships
        WHERE profile_hash = ? AND eligibility_status = ?
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
