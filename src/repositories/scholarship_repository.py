# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship

SCHEMA_COLUMNS = {
    "category": "TEXT NOT NULL DEFAULT 'other'",
    "notice_kind": "TEXT NOT NULL DEFAULT 'unknown'",
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

    # 初始化資料庫路徑並建立資料表。
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()
        self._migrate_schema()

    # 建立完整資料表與唯一索引。
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

    # 補齊舊版資料表缺少的狀態欄位。
    def _migrate_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            existing = self._column_names(conn)
            for name, definition in SCHEMA_COLUMNS.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE scholarships ADD COLUMN {name} {definition}")
            self._fill_discovered_at(conn)
            conn.commit()

    # 讀取目前資料表欄位名稱。
    def _column_names(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(scholarships)").fetchall()
        return {row[1] for row in rows}

    # 補齊舊資料的 discovered_at。
    def _fill_discovered_at(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE scholarships SET discovered_at = ? WHERE discovered_at IS NULL",
            [self._now_iso()],
        )

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
        rows = [self._discovery_row(item) for item in scholarships]
        query = """
        INSERT OR IGNORE INTO scholarships (
            source, title, published_date, source_url, category, notice_kind,
            content_hash, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.executemany(query, rows)
            conn.commit()
        return max(cursor.rowcount, 0)

    # 建立單筆公告寫入資料。
    def _discovery_row(self, item: Scholarship) -> tuple[str, ...]:
        return (
            item.source,
            item.title,
            item.published_date,
            item.source_url,
            item.category,
            item.notice_kind,
            item.content_hash,
            self._now_iso(),
        )

    # 取出目前所有尚未基準化或通知的公告。
    def list_pending(self) -> list[Scholarship]:
        query = self._select_query("notified_at IS NULL AND baseline_at IS NULL")
        return self._query_scholarships(query, [])

    # 取出尚未用目前背景設定完成評估的公告。
    def list_for_evaluation(self, profile_hash: str) -> list[Scholarship]:
        condition = (
            "notified_at IS NULL AND baseline_at IS NULL "
            "AND (eligibility_status IS NULL OR profile_hash IS NULL OR profile_hash != ?)"
        )
        return self._query_scholarships(self._select_query(condition), [profile_hash])

    # 取出符合推播狀態且屬於申請型的公告。
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

    # 建立讀取 Scholarship 所需的統一查詢。
    def _select_query(self, condition: str) -> str:
        return f"""
        SELECT source, title, published_date, source_url, category, content_hash,
               COALESCE(notice_kind, 'unknown'),
               COALESCE(eligibility_status, ''), COALESCE(eligibility_reason, '')
        FROM scholarships
        WHERE {condition}
        ORDER BY published_date DESC, id DESC
        """

    # 執行查詢並轉換成 Scholarship 清單。
    def _query_scholarships(
        self,
        query: str,
        params: list[str],
    ) -> list[Scholarship]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._to_scholarship(row) for row in rows]

    # 將 SQLite 資料列轉換為 Scholarship。
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
        )

    # 保存公告用途與個人資格判斷。
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

    # 統計指定背景設定下的資格判斷數量。
    def count_eligibility(self, profile_hash: str, status: str) -> int:
        query = """
        SELECT COUNT(1) FROM scholarships
        WHERE profile_hash = ? AND eligibility_status = ?
          AND notified_at IS NULL AND baseline_at IS NULL
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(query, [profile_hash, status]).fetchone()
        return int(row[0]) if row else 0

    # 將指定公告標記為歷史基準，不再推播。
    def mark_baseline(self, content_hashes: list[str]) -> int:
        return self._mark_time("baseline_at", content_hashes)

    # 將指定公告標記為已通知。
    def mark_notified(self, content_hashes: list[str]) -> int:
        return self._mark_time("notified_at", content_hashes)

    # 寫入指定時間欄位。
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
