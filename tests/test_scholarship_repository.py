# -*- coding: utf-8 -*-

from contextlib import closing
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
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT baseline_at, notified_at FROM scholarships WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] is None


# 驗證只有 eligible 狀態會進入預設推播清單。
def test_repository_filters_notifiable_status(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    eligible = _build_item("適合獎學金", "2026-07-01", "https://example.com/eligible")
    review = _build_item("待確認獎學金", "2026-07-02", "https://example.com/review")
    rejected = _build_item("不適合獎學金", "2026-07-03", "https://example.com/rejected")
    profile_hash = "profile-a"
    repo.discover([eligible, review, rejected])

    repo.mark_eligibility(eligible.content_hash, "eligible", "符合", profile_hash)
    repo.mark_eligibility(review.content_hash, "review", "待確認", profile_hash)
    repo.mark_eligibility(rejected.content_hash, "ineligible", "不符合", profile_hash)

    default_items = repo.list_notifiable(profile_hash, include_review=False)
    review_items = repo.list_notifiable(profile_hash, include_review=True)

    assert [item.content_hash for item in default_items] == [eligible.content_hash]
    assert {item.content_hash for item in review_items} == {
        eligible.content_hash,
        review.content_hash,
    }
    assert default_items[0].eligibility_reason == "符合"


# 驗證個人背景變更後既有公告會重新進入評估清單。
def test_repository_re_evaluates_when_profile_changes(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    item = _build_item("背景重評獎學金", "2026-07-01", "https://example.com/profile")
    repo.discover([item])
    repo.mark_eligibility(item.content_hash, "eligible", "符合", "profile-a")

    same_profile = repo.list_for_evaluation("profile-a")
    changed_profile = repo.list_for_evaluation("profile-b")

    assert same_profile == []
    assert [record.content_hash for record in changed_profile] == [item.content_hash]
