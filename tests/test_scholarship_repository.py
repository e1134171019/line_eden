# -*- coding: utf-8 -*-

from pathlib import Path
import sqlite3

from src.models.scholarship import Scholarship
from src.models.announcement_revision import (
    AnnouncementRevision,
    RevisionObservationStatus,
)
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


# 同一來源網址的 listing metadata 更新不新增資料，並保留原本狀態 row。
def test_repository_uses_stable_announcement_identity(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    original = _build_item("舊標題獎學金", "2026-07-01", "https://example.com/stable")
    updated = _build_item("更新標題獎學金", "2026-08-01", "https://example.com/stable")

    assert repo.discover([original]) == 1
    assert repo.discover([updated]) == 0

    pending = repo.list_pending()
    assert len(pending) == 1
    assert pending[0].title == updated.title
    assert pending[0].published_date == updated.published_date
    assert pending[0].content_hash == original.content_hash
    assert pending[0].announcement_id == original.announcement_id


# revision 內容改變時，repository 會原子清除先前通知與資格狀態。
def test_repository_changed_revision_reopens_lifecycle(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    item = _build_item("能源獎學金", "2026-07-01", "https://example.com/revision")
    repo.discover([item])
    initial = repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-a", "policy-a")
    )
    repo.mark_eligibility(item.content_hash, "eligible", "符合", "profile-a")
    repo.mark_notified([item.content_hash])

    unchanged = repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-a", "policy-b")
    )
    changed = repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-b", "policy-b")
    )

    assert initial.status is RevisionObservationStatus.INITIALIZED
    assert unchanged.status is RevisionObservationStatus.UNCHANGED
    assert changed.status is RevisionObservationStatus.CHANGED
    reopened = repo.list_for_evaluation("profile-a")
    assert [record.content_hash for record in reopened] == [item.content_hash]


# 歷史基準仍要建立 revision，內容改變後必須重新開啟生命週期。
def test_repository_changed_baseline_revision_becomes_pending(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    item = _build_item("歷史能源獎學金", "2026-07-01", "https://example.com/baseline")
    repo.discover([item])
    repo.mark_baseline_announcements([item.announcement_id])

    candidates = repo.list_revision_candidates([item.announcement_id])
    initial = repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-a", "policy-a")
    )
    unchanged_pending = repo.list_pending()
    changed = repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-b", "policy-a")
    )

    assert [record.announcement_id for record in candidates] == [item.announcement_id]
    assert initial.status is RevisionObservationStatus.INITIALIZED
    assert unchanged_pending == []
    assert changed.status is RevisionObservationStatus.CHANGED
    assert [record.announcement_id for record in repo.list_pending()] == [
        item.announcement_id
    ]


# 舊 schema 啟動時會相容補齊 identity 與 revision 欄位。
def test_repository_migrates_legacy_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE scholarships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                published_date TEXT NOT NULL,
                source_url TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            INSERT INTO scholarships (
                source, title, published_date, source_url, content_hash
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ["lhu", "舊資料獎學金", "2026-01-01", "https://example.com/old", "old"],
        )
        conn.execute(
            """
            INSERT INTO scholarships (
                source, title, published_date, source_url, content_hash
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                "lhu",
                "舊資料獎學金（更新）",
                "2026-01-02",
                "https://example.com/old",
                "old-revision",
            ],
        )
        conn.commit()

    repository = ScholarshipRepository(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scholarships)")}
        rows = conn.execute(
            "SELECT announcement_id, revision_hash FROM scholarships"
        ).fetchall()
    assert {"announcement_id", "revision_hash", "extraction_policy_hash"} <= columns
    assert len(rows) == 2
    assert len(rows[0][0]) == 64
    assert rows[0][0] == rows[1][0]
    assert rows[0][1] is None
    assert len(repository.list_pending()) == 1
    assert repository.mark_baseline_announcements([rows[0][0]]) == 1
    assert repository.list_pending() == []


# 管道送達狀態必須綁定目前 revision，不能沿用舊版成功紀錄。
def test_notification_delivery_is_scoped_to_current_revision(tmp_path: Path) -> None:
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    item = _build_item("能源獎學金", "2026-08-01", "https://example.com/delivery")
    repo.discover([item])
    repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-a", "policy-a")
    )

    assert repo.load_undelivered_hashes([item.content_hash], "line") == {
        item.content_hash
    }
    assert repo.save_notification_delivery([item.content_hash], "line") == 1
    assert repo.load_undelivered_hashes([item.content_hash], "line") == set()
    assert repo.save_notified_if_delivered([item.content_hash], ("line",)) == 1

    repo.observe_revision(
        AnnouncementRevision(item.announcement_id, "revision-b", "policy-a")
    )

    assert repo.load_undelivered_hashes([item.content_hash], "line") == {
        item.content_hash
    }
    assert repo.list_pending() != []
