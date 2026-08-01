# -*- coding: utf-8 -*-

from dataclasses import replace
from typing import Any

from src.models.announcement_revision import build_revision_hash
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import (
    ELIGIBILITY_NOT_APPLICABLE,
    AuditRecord,
    EvaluationOutcome,
    ScholarshipService,
)


class RevisionAwareScholarshipService(ScholarshipService):
    """追蹤本輪公告 revision，實質改版才重開評估與通知。"""

    repository: ScholarshipRepository

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_hashes: list[str] = []

    def _collect_and_discover(self) -> list[Scholarship]:
        raw = self.collector.collect()
        collected = self._filter_collected(raw)
        self.repository.discover(collected)
        self._current_hashes = [item.content_hash for item in collected]
        return collected

    def _evaluate_pending(self, profile_hash: str) -> None:
        processed: set[str] = set()
        for item in self.repository.list_by_hashes(self._current_hashes):
            fetch_result = self._fetch_audit_result(item)
            revision_hash = build_revision_hash(fetch_result)
            self.repository.register_revision(item.content_hash, revision_hash)
            processed.add(item.content_hash)
            if not self.repository.needs_evaluation(item.content_hash, profile_hash):
                continue
            outcome = self._evaluate_fetch_result(item, fetch_result)
            self._persist_outcome(item.content_hash, profile_hash, outcome)

        for item in self.repository.list_for_evaluation(profile_hash):
            if item.content_hash in processed:
                continue
            outcome = self._evaluate_item(item)
            self._persist_outcome(item.content_hash, profile_hash, outcome)

    def _persist_outcome(
        self,
        content_hash: str,
        profile_hash: str,
        outcome: EvaluationOutcome,
    ) -> None:
        excluded = (
            outcome.decision.reason_text()
            if outcome.decision.status == ELIGIBILITY_NOT_APPLICABLE
            else ""
        )
        self.repository.mark_eligibility(
            content_hash,
            outcome.decision.status,
            outcome.decision.reason_text(),
            profile_hash,
            outcome.notice_kind,
            outcome.application_status,
            excluded,
            outcome.decision.manual_checks,
            outcome.decision.review_kind,
            outcome.evidence.score,
            outcome.evidence.status,
        )

    def _build_audit_record(self, item: Scholarship) -> AuditRecord:
        record = super()._build_audit_record(item)
        revision_hash = build_revision_hash(record.fetch_result)
        return replace(record, item=replace(record.item, revision_hash=revision_hash))
