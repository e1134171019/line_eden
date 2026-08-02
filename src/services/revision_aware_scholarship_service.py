# -*- coding: utf-8 -*-

from dataclasses import replace
from typing import Any

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.evaluators.eligibility_evaluator import (
    INELIGIBLE,
    EligibilityDecision,
)
from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import EXPIRED, STALE_UNKNOWN
from src.models.announcement_revision import (
    build_announcement_id,
    build_revision_hash,
)
from src.models.eligibility_axes import derive_action_status
from src.models.scholarship import Scholarship
from src.repositories.announcement_revision_repository import (
    AnnouncementRevisionRepository,
)
from src.services.scholarship_service import (
    ELIGIBILITY_NOT_APPLICABLE,
    EvaluationOutcome,
    ScholarshipService,
    ServiceResult,
)
from src.services.structured_shadow_comparison import StructuredShadowComparison
from src.services.gemini_fallback_service import GeminiAnalysisDiagnostic


class RevisionAwareScholarshipService(ScholarshipService):
    """在既有服務前加 revision 與結構化硬性不符安全閘門。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.revision_repository = AnnouncementRevisionRepository(self.repository.db_path)
        self._revision_fetch_cache: dict[str, DetailFetchResult] = {}
        self._pre_veto_decisions: dict[str, EligibilityDecision] = {}

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

    def _evaluate_item(self, item: Scholarship) -> EvaluationOutcome:
        fetch_result = self._revision_fetch_cache.get(item.content_hash)
        if fetch_result is None:
            return super()._evaluate_item(item)
        return self._evaluate_fetch_result(item, fetch_result)

    # Structured 模型只抽取；deterministic evaluator 的明確 FAIL 才能否決 legacy。
    def _evaluate_fetch_result(
        self,
        item: Scholarship,
        fetch_result: DetailFetchResult,
    ) -> EvaluationOutcome:
        outcome = super()._evaluate_fetch_result(item, fetch_result)
        self._pre_veto_decisions[item.content_hash] = outcome.decision
        return self._apply_structured_ineligible_veto(item, fetch_result, outcome)

    def _apply_structured_ineligible_veto(
        self,
        item: Scholarship,
        fetch_result: DetailFetchResult,
        outcome: EvaluationOutcome,
    ) -> EvaluationOutcome:
        if not self.gemini_text_analysis or not self.structured_evaluator or not self.profile:
            return outcome
        if outcome.notice_kind != APPLICATION:
            return outcome
        if outcome.application_status in {EXPIRED, STALE_UNKNOWN}:
            return outcome
        if outcome.decision.status in {INELIGIBLE, ELIGIBILITY_NOT_APPLICABLE}:
            return outcome
        if fetch_result.source.status == "error":
            return outcome
        if not (fetch_result.body_text.strip() or fetch_result.extracted_attachments):
            return outcome

        analysis = self.gemini_text_analysis.analyze(item.title, fetch_result)
        if analysis.extraction is None:
            return outcome
        structured = self.structured_evaluator.evaluate(analysis.extraction, self.profile)
        if structured.decision.status != INELIGIBLE:
            return outcome
        action_status = derive_action_status(
            INELIGIBLE,
            outcome.evidence.status,
            outcome.notice_kind,
            outcome.application_status,
        )
        return replace(
            outcome,
            decision=structured.decision,
            action_status=action_status,
        )

    # Audit 仍以安全閘門前的 legacy 結果製作分歧明細，保留可追溯性。
    def _build_structured_shadow(
        self,
        item: Scholarship,
        legacy: EligibilityDecision,
        notice_kind: str,
        application_status: str,
        fetch_result: DetailFetchResult,
    ) -> tuple[
        StructuredShadowComparison | None,
        str,
        GeminiAnalysisDiagnostic | None,
    ]:
        original = self._pre_veto_decisions.get(item.content_hash, legacy)
        return super()._build_structured_shadow(
            item,
            original,
            notice_kind,
            application_status,
            fetch_result,
        )
