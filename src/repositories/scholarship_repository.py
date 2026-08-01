# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from src.models.announcement_revision import (
    AnnouncementRevision,
    RevisionObservation,
    RevisionObservationStatus,
)
from src.models.scholarship import Scholarship, build_announcement_id

SCHEMA_COLUMNS = {
    "announcement_id": "TEXT",
    "category": "TEXT NOT NULL DEFAULT 'other'",
    "notice_kind": "TEXT NOT NULL DEFAULT 'unknown'",
    "discovered_at": "TEXT",
    "baseline_at": "TEXT",
    "notified_at": "TEXT",
    "eligibility_status": "TEXT",
    "eligibility_reason": "TEXT",
    "profile_hash": "TEXT",
    "evaluated_at": "TEXT",
    "revision_hash": "TEXT",
    "extraction_policy_hash": "TEXT",
    "revision_observed_at": "TEXT",
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
        scholarship_query = """
        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            published_date TEXT NOT NULL,
            source_url TEXT NOT NULL,
            announcement_id TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            notice_kind TEXT NOT NULL DEFAULT 'unknown',
            content_hash TEXT NOT NULL UNIQUE,
            discovered_at TEXT NOT NULL,
            baseline_at TEXT,
            notified_at TEXT,
            eligibility_status TEXT,
            eligibility_reason TEXT,
            profile_hash TEXT,
            evaluated_at TEXT,
            revision_hash TEXT,
            extraction_policy_hash TEXT,
            revision_observed_at TEXT
        )
        """
        delivery_query = """
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            content_hash TEXT NOT NULL,
            revision_key TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            PRIMARY KEY (content_hash, revision_key, channel_id)
        )
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(scholarship_query)
            conn.execute(delivery_query)
            conn.commit()

    # 補齊舊版資料表缺少的狀態欄位。
    def _migrate_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            existing = self._column_names(conn)
            for name, definition in SCHEMA_COLUMNS.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE scholarships ADD COLUMN {name} {definition}")
            self._fill_discovered_at(conn)
            self._fill_announcement_ids(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scholarships_announcement_id "
                "ON scholarships(announcement_id)"
            )
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

    # 為既有資料補上不受標題與日期影響的穩定公告識別碼。
    def _fill_announcement_ids(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT id, source, source_url FROM scholarships "
            "WHERE announcement_id IS NULL OR announcement_id = ''"
        ).fetchall()
        updates = [
            (build_announcement_id(row[1], row[2]), row[0])
            for row in rows
        ]
        if updates:
            conn.executemany(
                "UPDATE scholarships SET announcement_id = ? WHERE id = ?",
                updates,
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
        inserted_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for item in scholarships:
                announcement_id = self._announcement_id(item)
                existing = conn.execute(
                    "SELECT 1 FROM scholarships WHERE announcement_id = ? LIMIT 1",
                    [announcement_id],
                ).fetchone()
                if existing:
                    self._refresh_listing_metadata(conn, item, announcement_id)
                    continue
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO scholarships (
                        source, title, published_date, source_url, announcement_id,
                        category, notice_kind, content_hash, discovered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._discovery_row(item),
                )
                inserted_count += max(cursor.rowcount, 0)
            conn.commit()
        return inserted_count

    # 更新同一公告在 listing 上可變的顯示欄位，但保留既有 row handle 與狀態。
    def _refresh_listing_metadata(
        self,
        conn: sqlite3.Connection,
        item: Scholarship,
        announcement_id: str,
    ) -> None:
        conn.execute(
            """
            UPDATE scholarships
            SET source = ?, title = ?, published_date = ?, source_url = ?, category = ?
            WHERE announcement_id = ?
            """,
            [
                item.source,
                item.title,
                item.published_date,
                item.source_url,
                item.category,
                announcement_id,
            ],
        )

    # 建立單筆公告寫入資料。
    def _discovery_row(self, item: Scholarship) -> tuple[str, ...]:
        return (
            item.source,
            item.title,
            item.published_date,
            item.source_url,
            self._announcement_id(item),
            item.category,
            item.notice_kind,
            item.content_hash,
            self._now_iso(),
        )

    # 相容尚未帶 announcement_id 的舊測試或外部呼叫端。
    def _announcement_id(self, item: Scholarship) -> str:
        return item.announcement_id or build_announcement_id(
            item.source,
            item.source_url,
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

    # 取出本輪仍出現在來源 listing、且未列為歷史基準的 revision 候選。
    def list_revision_candidates(
        self,
        announcement_ids: list[str],
    ) -> list[Scholarship]:
        unique_ids = list(dict.fromkeys(value for value in announcement_ids if value))
        if not unique_ids:
            return []
        placeholders = ",".join(["?"] * len(unique_ids))
        condition = (
            "baseline_at IS NULL "
            f"AND announcement_id IN ({placeholders})"
        )
        return self._query_scholarships(
            self._select_query(condition),
            unique_ids,
        )

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
               COALESCE(announcement_id, ''),
               COALESCE(notice_kind, 'unknown'),
               COALESCE(eligibility_status, ''), COALESCE(eligibility_reason, '')
        FROM scholarships
        WHERE {condition}
          AND id = (
              SELECT MIN(canonical.id)
              FROM scholarships AS canonical
              WHERE canonical.announcement_id = scholarships.announcement_id
          )
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
            announcement_id=row[6],
            notice_kind=row[7],
            eligibility_status=row[8],
            eligibility_reason=row[9],
        )

    # 保存正文 revision；內容變更時清除通知與評估狀態，交由服務重新判斷。
    def observe_revision(
        self,
        revision: AnnouncementRevision,
        reset_on_change: bool = True,
    ) -> RevisionObservation:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT COALESCE(revision_hash, ''), baseline_at
                FROM scholarships
                WHERE announcement_id = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                [revision.announcement_id],
            ).fetchone()
            if row is None:
                return RevisionObservation(RevisionObservationStatus.NOT_FOUND)
            previous_hash = str(row[0])
            status = _revision_observation_status(
                previous_hash,
                revision.revision_hash,
            )
            should_reset = (
                reset_on_change
                and status is RevisionObservationStatus.CHANGED
                and row[1] is None
            )
            if should_reset:
                self._save_changed_revision(
                    conn,
                    revision.announcement_id,
                    revision.revision_hash,
                    revision.extraction_policy_hash,
                )
            else:
                conn.execute(
                    """
                    UPDATE scholarships
                    SET revision_hash = ?, extraction_policy_hash = ?,
                        revision_observed_at = ?
                    WHERE announcement_id = ?
                    """,
                    [
                        revision.revision_hash,
                        revision.extraction_policy_hash,
                        self._now_iso(),
                        revision.announcement_id,
                    ],
                )
            conn.commit()
        return RevisionObservation(status, previous_hash)

    # 原子保存內容變更並重開此公告的評估與通知生命週期。
    def _save_changed_revision(
        self,
        conn: sqlite3.Connection,
        announcement_id: str,
        revision_hash: str,
        extraction_policy_hash: str,
    ) -> None:
        conn.execute(
            """
            UPDATE scholarships
            SET revision_hash = ?, extraction_policy_hash = ?,
                revision_observed_at = ?, notified_at = NULL,
                notice_kind = 'unknown', eligibility_status = NULL,
                eligibility_reason = NULL, profile_hash = NULL, evaluated_at = NULL
            WHERE announcement_id = ? AND baseline_at IS NULL
            """,
            [
                revision_hash,
                extraction_policy_hash,
                self._now_iso(),
                announcement_id,
            ],
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
        SELECT COUNT(DISTINCT announcement_id) FROM scholarships
        WHERE profile_hash = ? AND eligibility_status = ?
          AND notified_at IS NULL AND baseline_at IS NULL
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(query, [profile_hash, status]).fetchone()
        return int(row[0]) if row else 0

    # 將指定公告標記為歷史基準，不再推播。
    def mark_baseline(self, content_hashes: list[str]) -> int:
        return self._mark_time("baseline_at", content_hashes)

    # 以穩定 identity 將歷史公告基準化，並以公告數而非 legacy row 數計數。
    def mark_baseline_announcements(self, announcement_ids: list[str]) -> int:
        unique_ids = list(dict.fromkeys(value for value in announcement_ids if value))
        if not unique_ids:
            return 0
        placeholders = ",".join(["?"] * len(unique_ids))
        count_query = f"""
        SELECT COUNT(DISTINCT announcement_id)
        FROM scholarships
        WHERE baseline_at IS NULL
          AND announcement_id IN ({placeholders})
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(count_query, unique_ids).fetchone()
            conn.execute(
                "UPDATE scholarships SET baseline_at = ? "
                f"WHERE announcement_id IN ({placeholders}) "
                "AND baseline_at IS NULL",
                [self._now_iso(), *unique_ids],
            )
            conn.commit()
        return int(row[0]) if row else 0

    # 將指定公告標記為已通知。
    def mark_notified(self, content_hashes: list[str]) -> int:
        return self._mark_time("notified_at", content_hashes)

    # 讀取指定管道尚未送達的公告 row handle。
    def load_undelivered_hashes(
        self,
        content_hashes: list[str],
        channel_id: str,
    ) -> set[str]:
        unique_hashes = list(dict.fromkeys(content_hashes))
        if not unique_hashes:
            return set()
        placeholders = ",".join(["?"] * len(unique_hashes))
        query = f"""
        SELECT scholarships.content_hash
        FROM scholarships
        LEFT JOIN notification_deliveries AS deliveries
          ON deliveries.content_hash = scholarships.content_hash
         AND deliveries.revision_key = {_revision_key_sql('scholarships')}
         AND deliveries.channel_id = ?
        WHERE scholarships.content_hash IN ({placeholders})
          AND deliveries.content_hash IS NULL
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, [channel_id, *unique_hashes]).fetchall()
        return {str(row[0]) for row in rows}

    # 保存單一管道已成功送達的公告 revision。
    def save_notification_delivery(
        self,
        content_hashes: list[str],
        channel_id: str,
    ) -> int:
        unique_hashes = list(dict.fromkeys(content_hashes))
        if not unique_hashes:
            return 0
        placeholders = ",".join(["?"] * len(unique_hashes))
        select_query = f"""
        SELECT content_hash, {_revision_key_sql('scholarships')}
        FROM scholarships
        WHERE content_hash IN ({placeholders})
        """
        with sqlite3.connect(self.db_path) as conn:
            revisions = conn.execute(select_query, unique_hashes).fetchall()
            rows = [
                (str(content_hash), str(revision_key), channel_id, self._now_iso())
                for content_hash, revision_key in revisions
            ]
            cursor = conn.executemany(
                """
                INSERT OR IGNORE INTO notification_deliveries (
                    content_hash, revision_key, channel_id, delivered_at
                ) VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return max(cursor.rowcount, 0)

    # 所有指定管道都完成目前 revision 後，才寫入 notified_at。
    def save_notified_if_delivered(
        self,
        content_hashes: list[str],
        channel_ids: tuple[str, ...],
    ) -> int:
        unique_hashes = list(dict.fromkeys(content_hashes))
        unique_channels = tuple(dict.fromkeys(channel_ids))
        if not unique_hashes or not unique_channels:
            return 0
        marked_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for content_hash in unique_hashes:
                marked_count += self._save_notified_row(
                    conn,
                    content_hash,
                    unique_channels,
                )
            conn.commit()
        return marked_count

    # 檢查單筆公告 delivery completeness 並原子寫入通知時間。
    def _save_notified_row(
        self,
        conn: sqlite3.Connection,
        content_hash: str,
        channel_ids: tuple[str, ...],
    ) -> int:
        placeholders = ",".join(["?"] * len(channel_ids))
        query = f"""
        UPDATE scholarships
        SET notified_at = ?
        WHERE content_hash = ? AND notified_at IS NULL AND baseline_at IS NULL
          AND (
              SELECT COUNT(DISTINCT deliveries.channel_id)
              FROM notification_deliveries AS deliveries
              WHERE deliveries.content_hash = scholarships.content_hash
                AND deliveries.revision_key = {_revision_key_sql('scholarships')}
                AND deliveries.channel_id IN ({placeholders})
          ) = ?
        """
        cursor = conn.execute(
            query,
            [self._now_iso(), content_hash, *channel_ids, len(channel_ids)],
        )
        return max(cursor.rowcount, 0)

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


def _revision_observation_status(
    previous_hash: str,
    revision_hash: str,
) -> RevisionObservationStatus:
    """比較舊、新 revision hash，不依賴 repository 狀態。"""
    if not previous_hash:
        return RevisionObservationStatus.INITIALIZED
    if previous_hash == revision_hash:
        return RevisionObservationStatus.UNCHANGED
    return RevisionObservationStatus.CHANGED


def _revision_key_sql(table_name: str) -> str:
    """純函式：建立 delivery 對應目前公告 revision 的 SQL 表達式。"""
    return f"COALESCE(NULLIF({table_name}.revision_hash, ''), {table_name}.content_hash)"
