# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.models.announcement_revision import (
    build_announcement_id,
    build_revision_hash,
)
from src.models.scholarship import Scholarship
from src.repositories.announcement_revision_repository import (
    AnnouncementRevisionRepository,
)
from src.services.scholarship_service import ScholarshipService, ServiceResult


class RevisionAwareScholarshipService(ScholarshipService):
    """在既有 ScholarshipService 前加一層薄 revision 觀察，不複製判斷流程。"""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.revision_repository = AnnouncementRevisionRepository(
            self.repository.db_path
        )
        self._revision_fetch_cache: dict[str, DetailFetchResult] = {}

    def run(self, dry_run: bool) -> ServiceResult:
        collected = self._collect_and_discover()
        self._refresh_revisions(collected)
        pending_items, counts = self._prepare_notifiable_items()
        pipeline = self._pipeline_counts(collected, pending_items)
        if dry_run:
            return self._build_dry_run_result(collected, pending_items, counts, pipeline)
        return self._run_live_mode(collected, pending_items, counts, pipeline)

    def _refresh_revisions(self, collected: list[Scholarship]) -> None:
        if not self._personalization_enabled():
            return
        for item in collected:
            fetch_result = self._fetch_audit_result(item)
            self._revision_fetch_cache[item.content_hash] = fetch_result
            if fetch_result.source.status == "error":
                continue
            self.revision_repository.observe(
                item.content_hash,
                build_announcement_id(item),
                build_revision_hash(item, fetch_result),
            )

    def _evaluate_item(self, item: Scholarship):  # type: ignore[no-untyped-def]
        fetch_result = self._revision_fetch_cache.get(item.content_hash)
        if fetch_result is None:
            return super()._evaluate_item(item)
        return self._evaluate_fetch_result(item, fetch_result)
