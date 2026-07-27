# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship


class ScholarshipRepository:
    """Scholarship 的 SQLite 存取層。"""

    # 初始化資料庫路徑並建立資料表。
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()
        self._migrate_schema()

    # 建立資料表與唯一索引。
    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            published_date TEXT NOT NULL,
            source_url TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            content_hash TEXT NOT NULL UNIQUE,
            discovered_at TEXT NOT NULL,
            baseline_at TEXT,
            notified_at TEXT
        )
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query)
            conn.commit()

    # 補齊舊版資料表欄位並填入預設值。
    def _migrate_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("PRAGMA table_info(scholarships)").fetchall()
            names = {row[1] for row in rows}
            if "category" not in names:
                conn.execute(
                    "ALTER TABLE scholarships ADD COLUMN category TEXT NOT NULL DEFAULT 'other'"
                )
            if "discovered_at" not in names:
                conn.execute("ALTER TABLE scholarships ADD COLUMN discovered_at TEXT")
                conn.execute(
                    "UPDATE scholarships SET discovered_at = COALESCE(created_at, notified_at, ?) "
                    "WHERE discovered_at IS NULL",
                    [self._now_iso()],
                )
            if "baseline_at" not in names:
                conn.execute("ALTER TABLE scholarships ADD COLUMN baseline_at TEXT")
            if "notified_at" not in names:
                conn.execute("ALTER TABLE scholarships ADD COLUMN notified_at TEXT")
            conn.commit()

    # 產生 UTC ISO 時間字串。
    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 取得資料庫目前是否無任何公告資料。
    def is_empty(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(1) FROM scholarships").fetchone()
        return bool(row and row[0] == 0)

    # 回傳輸入 content_hash 中已存在資料庫的集合。
    def get_existing_hashes(self, content_hashes: list[str]) -> set[str]:
        if not content_hashes:
            return set()
        placeholders = ",".join(["?"] * len(content_hashes))
        query = f"SELECT content_hash FROM scholarships WHERE content_hash IN ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, content_hashes).fetchall()
        return {row[0] for row in rows}

    # 新增已蒐集公告，重複資料將被忽略。
    def discover(self, scholarships: list[Scholarship]) -> int:
        if not scholarships:
            return 0
        now = self._now_iso()
        rows = [
            (
                item.source,
                item.title,
                item.published_date,
                item.source_url,
                item.category,
                item.content_hash,
                now,
            )
            for item in scholarships
        ]
        query = """
        INSERT OR IGNORE INTO scholarships (
            source, title, published_date, source_url, category, content_hash, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.executemany(query, rows)
            conn.commit()
            return cursor.rowcount if cursor.rowcount >= 0 else 0

    # 取出目前所有待通知公告。
    def list_pending(self) -> list[Scholarship]:
        query = """
        SELECT source, title, published_date, source_url, category, content_hash
        FROM scholarships
        WHERE notified_at IS NULL AND baseline_at IS NULL
        ORDER BY published_date DESC, id DESC
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query).fetchall()
        return [
            Scholarship(
                source=row[0],
                title=row[1],
                published_date=row[2],
                source_url=row[3],
                category=row[4],
                content_hash=row[5],
            )
            for row in rows
        ]

    # 將指定公告標記為歷史基準，不再推播。
    def mark_baseline(self, content_hashes: list[str]) -> int:
        if not content_hashes:
            return 0
        now = self._now_iso()
        placeholders = ",".join(["?"] * len(content_hashes))
        query = (
            "UPDATE scholarships "
            "SET baseline_at = ? "
            f"WHERE content_hash IN ({placeholders}) "
            "AND baseline_at IS NULL AND notified_at IS NULL"
        )
        params = [now, *content_hashes]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount if cursor.rowcount >= 0 else 0

    # 將指定公告標記為已通知，並更新通知時間。
    def mark_notified(self, content_hashes: list[str]) -> int:
        if not content_hashes:
            return 0
        now = self._now_iso()
        placeholders = ",".join(["?"] * len(content_hashes))
        query = (
            "UPDATE scholarships "
            "SET notified_at = ? "
            f"WHERE content_hash IN ({placeholders}) "
            "AND notified_at IS NULL"
        )
        params = [now, *content_hashes]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount if cursor.rowcount >= 0 else 0
