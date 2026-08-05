# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.repositories.sqlite_connection import open_database


@dataclass(frozen=True)
class GeminiCacheEntry:
    """不含個人背景的 Gemini 文件抽取快取。"""

    cache_key: str
    document_hash: str
    source_url: str
    model: str
    prompt_version: str
    status: str
    extracted_json: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error: str


class GeminiCacheRepository:
    """以獨立 SQLite 保存 Gemini 文件結果，避免重複計費。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()

    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS gemini_document_cache (
            cache_key TEXT PRIMARY KEY,
            document_hash TEXT NOT NULL,
            source_url TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            status TEXT NOT NULL,
            extracted_json TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
        with open_database(self.db_path) as conn:
            conn.execute(query)

    def get(self, cache_key: str) -> GeminiCacheEntry | None:
        query = """
        SELECT cache_key, document_hash, source_url, model, prompt_version,
               status, extracted_json, input_tokens, output_tokens, total_tokens, error
        FROM gemini_document_cache
        WHERE cache_key = ?
        """
        with open_database(self.db_path) as conn:
            row = conn.execute(query, [cache_key]).fetchone()
        return GeminiCacheEntry(*row) if row else None

    def save(self, entry: GeminiCacheEntry) -> int:
        query = """
        INSERT OR IGNORE INTO gemini_document_cache (
            cache_key, document_hash, source_url, model, prompt_version,
            status, extracted_json, input_tokens, output_tokens, total_tokens,
            error, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = [
            entry.cache_key,
            entry.document_hash,
            entry.source_url,
            entry.model,
            entry.prompt_version,
            entry.status,
            entry.extracted_json,
            entry.input_tokens,
            entry.output_tokens,
            entry.total_tokens,
            entry.error,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ]
        with open_database(self.db_path) as conn:
            cursor = conn.execute(query, values)
        return max(cursor.rowcount, 0)

    def delete(self, cache_key: str) -> int:
        with open_database(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM gemini_document_cache WHERE cache_key = ?",
                [cache_key],
            )
        return max(cursor.rowcount, 0)
