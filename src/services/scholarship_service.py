# -*- coding: utf-8 -*-

from dataclasses import dataclass, replace
from typing import Callable, cast

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ResourceDiagnostic,
    RULES_STATUS_RESOLVED,
    RULES_STATUS_UNKNOWN,
)
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityDecision,
    EligibilityEvaluator,
)
from src.evaluators.evaluator_input_builder import build_evaluator_input
from src.evaluators.notice_classifier import APPLICATION, UNKNOWN, classify_notice
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.formatters.scholarship_message_formatter import (
    build_summary_message,
    split_scholarships,
)
from src.models.evaluator_input import (
    GEMINI_RULE_COMPLETE,
    GEMINI_RULE_NONE,
    GEMINI_RULE_PARTIAL_EXCLUSIONS,
    EvaluatorInput,
    GeminiRuleScope,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.gemini_fallback_service import (
    GeminiAnalysisDiagnostic,
    GeminiFallbackService,
)
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService
from src.services.structured_shadow_comparison import (
    StructuredShadowComparison,
    compare_legacy_and_structured,
)


@dataclass(frozen=True)
class ServiceResult:
    collected: list[Scholarship]
    pending_items: list[Scholarship]
    notified_count: int
    baseline_count: int
    message: str
    eligible_count: int = 0
    review_count: int = 0
    ineligible_count: int = 0
    gemini_calls: int = 0
    gemini_cache_hits: int = 0
    gemini_input_tokens: int = 0
    gemini_output_tokens: int = 0


@dataclass(frozen=True)
class AuditRecord:
    """單筆歷史公告的 legacy 結果、structured shadow 與擷取診斷。"""

    item: Scholarship
    detail_excerpt: str
    fetch_result: DetailFetchResult
    gemini_diagnostic: GeminiAnalysisDiagnostic | None = None
    structured_shadow: StructuredShadowComparison | None = None
    shadow_status: str = "not_run"
    structured_gemini_diagnostic: GeminiAnalysisDiagnostic | None = None


@dataclass(frozen=True)
class AuditResult:
    """不修改獎學金狀態的歷史公告稽核結果。"""

    records: list[AuditRecord]
    eligible_count: int
    review_count: int
    ineligible_count: int
    message: str
    gemini_calls: int = 0
    gemini_cache_hits: int = 0
    gemini_input_tokens: int = 0
    gemini_output_tokens: int = 0
    structured_evaluated_count: int = 0
    structured_changed_count: int = 0
    structured_deferred_count: int = 0
    structured_error_count: int = 0


class ScholarshipService:
    """協調蒐集、公告分類、資格判斷與 LINE 通知流程。"""

    def __init__(
        self,
        collector: BaseCollector,
        repository: ScholarshipRepository,
        notifier: Callable[[str], None],
        include_keywords: tuple[str, ...] | None,
        summary_batch_size: int,
        detail_fetcher: AnnouncementDetailFetcher | None = None,
        evaluator: EligibilityEvaluator | None = None,
        profile: StudentProfile | None = None,
        notify_review_items: bool = False,
        gemini_fallback: GeminiFallbackService | None = None,
        gemini_text_analysis: GeminiTextAnalysisService | None = None,
        structured_evaluator: StructuredEligibilityEvaluator | None = None,
    ) -> None:
        self.collector = collector
        self.repository = repository
        self.notifier = notifier
        self.include_keywords = include_keywords or tuple()
        self.summary_batch_size = summary_batch_size
        self.detail_fetcher = detail_fetcher
        self.evaluator = evaluator
        self.profile = profile
        self.notify_review_items = notify_review_items
        self.gemini_fallback = gemini_fallback
        self.gemini_text_analysis = gemini_text_analysis
        self.structured_evaluator = structured_evaluator

    def run(self, dry_run: bool) -> ServiceResult:
        collected = self._collect_and_discover()
        pending_items, counts = self._prepare_notifiable_items()
        if dry_run:
            return self._build_dry_run_result(collected, pending_items, counts)
        return self._run_live_mode(collected, pending_items, counts)

    def audit(self) -> AuditResult:
        collected = self._filter_collected(self.collector.collect())
        records = [self._build_audit_record(item) for item in collected]
        eligible = self._count_audit_status(records, ELIGIBLE)
        review = self._count_audit_status(records, REVIEW)
        ineligible = self._count_audit_status(records, INELIGIBLE)
        structured_evaluated = sum(record.structured_shadow is not None for record in records)
        structured_changed = sum(
            bool(record.structured_shadow and record.structured_shadow.changed)
            for record in records
        )
        structured_deferred = sum(
            record.shadow_status == "budget_deferred" for record in records
        )
        structured_errors = sum(
            record.shadow_status in {"text_error", "text_cached_error"}
            for record in records
        )
        message = f"已稽核 {len(records)} 筆公告，不會傳送 LINE 或修改獎學金狀態。"
        if self.gemini_fallback or self.gemini_text_analysis:
            message += " Gemini 結果只會寫入獨立文件快取與 shadow artifact。"
        return AuditResult(
            records,
            eligible,
            review,
            ineligible,
            message,
            *self._gemini_usage(),
            structured_evaluated,
            structured_changed,
            structured_deferred,
            structured_errors,
        )

    def initialize_baseline(self) -> ServiceResult:
        collected = self._collect_and_discover()
        hashes = [item.content_hash for item in collected]
        baseline_count = self.repository.mark_baseline(hashes)
        pending_items = self.repository.list_pending()
        return ServiceResult(
            collected,
            pending_items,
            0,
            baseline_count,
            f"已設定 {baseline_count} 筆歷史基準。",
        )

    def _collect_and_discover(self) -> list[Scholarship]:
        collected = self._filter_collected(self.collector.collect())
        self.repository.discover(collected)
        return collected

    def _filter_collected(self, collected: list[Scholarship]) -> list[Scholarship]:
        if not self.include_keywords:
            return collected
        return [
            item
            for item in collected
            if any(keyword in item.title for keyword in self.include_keywords)
        ]

    def _prepare_notifiable_items(
        self,
    ) -> tuple[list[Scholarship], tuple[int, int, int]]:
        if not self._personalization_enabled():
            pending = self.repository.list_pending()
            return pending, (len(pending), 0, 0)
        assert self.profile is not None
        profile_hash = self.profile.fingerprint()
        self._evaluate_pending(profile_hash)
        items = self.repository.list_notifiable(profile_hash, self.notify_review_items)
        counts = self._eligibility_counts(profile_hash)
        return items, counts

    def _personalization_enabled(self) -> bool:
        return all((self.detail_fetcher, self.evaluator, self.profile))

    def _evaluate_pending(self, profile_hash: str) -> None:
        for item in self.repository.list_for_evaluation(profile_hash):
            decision, notice_kind, _, _ = self._evaluate_item(item)
            self.repository.mark_eligibility(
                item.content_hash,
                decision.status,
                decision.reason_text(),
                profile_hash,
                notice_kind,
            )

    def _evaluate_item(
        self,
        item: Scholarship,
    ) -> tuple[EligibilityDecision, str, str, GeminiAnalysisDiagnostic | None]:
        fetch_result = self._fetch_audit_result(item)
        return self._evaluate_fetch_result(item, fetch_result)

    def _evaluate_fetch_result(
        self,
        item: Scholarship,
        fetch_result: DetailFetchResult,
    ) -> tuple[EligibilityDecision, str, str, GeminiAnalysisDiagnostic | None]:
        if fetch_result.source.status == "error":
            decision = EligibilityDecision(REVIEW, ("公告正文讀取失敗，暫不推播。",))
            return decision, UNKNOWN, "", None

        base_input = build_evaluator_input(fetch_result)
        detail_text = fetch_result.eligibility_text()
        decision, notice_kind = self._evaluate_detail(item, detail_text, base_input)
        if (
            notice_kind != APPLICATION
            or decision.status != REVIEW
            or not self.gemini_fallback
        ):
            return decision, notice_kind, detail_text, None

        fallback = self.gemini_fallback.analyze(item.title, fetch_result)
        if fallback is None or not fallback.rule_text:
            diagnostic = fallback.diagnostic if fallback else None
            return decision, notice_kind, detail_text, diagnostic

        scope = _gemini_rule_scope(fallback.diagnostic.status)
        effective_rules_status = (
            RULES_STATUS_RESOLVED
            if scope == GEMINI_RULE_COMPLETE
            else fetch_result.rules_status
        )
        evaluator_input = build_evaluator_input(
            fetch_result,
            fallback.rule_text,
            gemini_rule_scope=scope,
            rules_status=effective_rules_status,
        )
        assert self.evaluator is not None
        assert self.profile is not None
        decision = self.evaluator.evaluate(item, evaluator_input, self.profile)
        return decision, notice_kind, detail_text, fallback.diagnostic

    def _evaluate_detail(
        self,
        item: Scholarship,
        detail_text: str,
        evaluator_input: EvaluatorInput,
    ) -> tuple[EligibilityDecision, str]:
        notice_kind = classify_notice(item.title, detail_text)
        if notice_kind != APPLICATION:
            reason = f"非申請型公告（{notice_kind}），不推播。"
            return EligibilityDecision(INELIGIBLE, (reason,)), notice_kind
        assert self.evaluator is not None
        assert self.profile is not None
        decision = self.evaluator.evaluate(item, evaluator_input, self.profile)
        return decision, notice_kind

    def _build_audit_record(self, item: Scholarship) -> AuditRecord:
        fetch_result = self._fetch_audit_result(item)
        decision, notice_kind, detail_text, gemini = self._evaluate_fetch_result(
            item,
            fetch_result,
        )
        shadow, shadow_status, shadow_gemini = self._build_structured_shadow(
            item,
            decision,
            notice_kind,
            fetch_result,
        )
        evaluated = replace(
            item,
            notice_kind=notice_kind,
            eligibility_status=decision.status,
            eligibility_reason=decision.reason_text(),
        )
        return AuditRecord(
            evaluated,
            self._excerpt(detail_text),
            fetch_result,
            gemini,
            shadow,
            shadow_status,
            shadow_gemini,
        )

    def _build_structured_shadow(
        self,
        item: Scholarship,
        legacy: EligibilityDecision,
        notice_kind: str,
        fetch_result: DetailFetchResult,
    ) -> tuple[
        StructuredShadowComparison | None,
        str,
        GeminiAnalysisDiagnostic | None,
    ]:
        if not self.gemini_text_analysis or not self.structured_evaluator or not self.profile:
            return None, "disabled", None
        if notice_kind != APPLICATION:
            return None, "not_application", None
        if legacy.status == INELIGIBLE:
            return None, "legacy_ineligible", None
        if fetch_result.source.status == "error":
            return None, "source_error", None
        if not (fetch_result.body_text.strip() or fetch_result.extracted_attachments):
            return None, "no_evidence", None
        analysis = self.gemini_text_analysis.analyze(item.title, fetch_result)
        if analysis.extraction is None:
            return None, analysis.diagnostic.status, analysis.diagnostic
        comparison = compare_legacy_and_structured(
            legacy,
            analysis.extraction,
            self.profile,
            self.structured_evaluator,
        )
        return comparison, "compared", analysis.diagnostic

    def _fetch_audit_result(self, item: Scholarship) -> DetailFetchResult:
        assert self.detail_fetcher is not None
        fetch_method = getattr(self.detail_fetcher, "fetch_with_diagnostics", None)
        if callable(fetch_method):
            typed_fetch = cast(
                Callable[[Scholarship], DetailFetchResult],
                fetch_method,
            )
            return typed_fetch(item)
        try:
            text = self.detail_fetcher.fetch_text(item)
        except Exception as error:
            source = ResourceDiagnostic(
                "source",
                item.source_url,
                "",
                "",
                0,
                "unknown",
                "error",
                0,
                _error_text(error),
            )
            return DetailFetchResult("", source, tuple(), 0)
        source = ResourceDiagnostic(
            "source",
            item.source_url,
            item.source_url,
            "text/plain",
            len(text.encode("utf-8")),
            "html",
            "success",
            len(text),
            "",
        )
        return DetailFetchResult(
            text,
            source,
            tuple(),
            0,
            body_text=text,
            rules_status=RULES_STATUS_UNKNOWN,
        )

    def _count_audit_status(self, records: list[AuditRecord], status: str) -> int:
        return sum(record.item.eligibility_status == status for record in records)

    def _excerpt(self, detail_text: str) -> str:
        normalized = " ".join(detail_text.split())
        return normalized[:160]

    def _eligibility_counts(self, profile_hash: str) -> tuple[int, int, int]:
        eligible = self.repository.count_eligibility(profile_hash, ELIGIBLE)
        review = self.repository.count_eligibility(profile_hash, REVIEW)
        ineligible = self.repository.count_eligibility(profile_hash, INELIGIBLE)
        return eligible, review, ineligible

    def _gemini_usage(self) -> tuple[int, int, int, int]:
        if self.gemini_fallback:
            summary = self.gemini_fallback.usage_summary()
        elif self.gemini_text_analysis:
            summary = self.gemini_text_analysis.limiter.summary()
        else:
            return 0, 0, 0, 0
        return summary.calls, summary.cache_hits, summary.input_tokens, summary.output_tokens

    def _build_dry_run_result(
        self,
        collected: list[Scholarship],
        pending_items: list[Scholarship],
        counts: tuple[int, int, int],
    ) -> ServiceResult:
        return ServiceResult(
            collected,
            pending_items,
            0,
            0,
            "dry-run，不會傳送 LINE。",
            *counts,
            *self._gemini_usage(),
        )

    def _run_live_mode(
        self,
        collected: list[Scholarship],
        pending_items: list[Scholarship],
        counts: tuple[int, int, int],
    ) -> ServiceResult:
        if not pending_items:
            return ServiceResult(
                collected,
                [],
                0,
                0,
                "沒有適合目前背景的待通知公告。",
                *counts,
                *self._gemini_usage(),
            )
        return self._notify_batches(collected, pending_items, counts)

    def _notify_batches(
        self,
        collected: list[Scholarship],
        pending_items: list[Scholarship],
        counts: tuple[int, int, int],
    ) -> ServiceResult:
        batches = split_scholarships(pending_items, self.summary_batch_size)
        notified_count = self._send_batches(batches)
        message = f"已送出 {len(batches)} 則摘要，共通知 {notified_count} 筆公告。"
        return ServiceResult(
            collected,
            pending_items,
            notified_count,
            0,
            message,
            *counts,
            *self._gemini_usage(),
        )

    def _send_batches(self, batches: list[list[Scholarship]]) -> int:
        notified_count = 0
        for index, batch in enumerate(batches, start=1):
            message = build_summary_message(batch, index, len(batches))
            self.notifier(message)
            hashes = [item.content_hash for item in batch]
            notified_count += self.repository.mark_notified(hashes)
        return notified_count


def _gemini_rule_scope(status: str) -> GeminiRuleScope:
    if status in {"success", "cache"}:
        return GEMINI_RULE_COMPLETE
    if status in {"partial_exclusion", "cache_partial_exclusion"}:
        return GEMINI_RULE_PARTIAL_EXCLUSIONS
    return GEMINI_RULE_NONE


def _error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"[:240]
