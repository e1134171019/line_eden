# -*- coding: utf-8 -*-

from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository


# 建立測試用 Scholarship 物件。
def _build_item(title: str, date_text: str, url: str) -> Scholarship:
    return Scholarship.from_raw("lhu", title, date_text, url)


# 驗證資料寫入、去重與已通知標記流程。
def test_repository_dedup_and_mark_notified(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    first = _build_item("A 獎學金公告", "2026-07-01", "https://example.com/a")
    second = _build_item("B 助學金公告", "2026-07-02", "https://example.com/b")

    inserted_first = repo.discover([first, second])
    inserted_second = repo.discover([first])
    existing = repo.get_existing_hashes([first.content_hash, "missing"])
    marked = repo.mark_notified([first.content_hash])

    assert inserted_first == 2
    assert inserted_second == 0
    assert first.content_hash in existing
    assert marked == 1
    assert [item.content_hash for item in repo.list_pending()] == [second.content_hash]


# 驗證 baseline 與 notified 欄位分別保存狀態。
def test_repository_baseline_state(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "scholarships.db"
    repo = ScholarshipRepository(db_path)
    item = _build_item("歷史獎學金", "2026-07-01", "https://example.com/history")

    repo.discover([item])
    marked = repo.mark_baseline([item.content_hash])

    assert marked == 1
    assert repo.list_pending() == []
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT baseline_at, notified_at FROM scholarships WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] is None
