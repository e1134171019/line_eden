# -*- coding: utf-8 -*-

from typing import Callable

from config import UNRESOLVED_ATTACHMENT_MARKER
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    RULES_STATUS_RESOLVED,
)
from src.evaluators.eligibility_evaluator import REVIEW, EligibilityDecision, EligibilityEvaluator
from src.evaluators.notice_classifier import APPLICATION, UNKNOWN
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.gemini_fallback_service import GeminiAnalysisDiagnostic, GeminiFallbackService
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService
from src.services.scholarship_service import ScholarshipService


class FullScholarshipService(ScholarshipService):
    """正式完整服務；profile、正文擷取器與 evaluator 均為必要依賴。"""

    def __init__(
        self,
        collector: BaseCollector,
        repository: ScholarshipRepository,
        notifier: Callable[[str], None],
        include_keywords: tuple[str, ...] | None,
        summary_batch_size: int,
        detail_fetcher: AnnouncementDetailFetcher,
        evaluator: EligibilityEvaluator,
        profile: StudentProfile,
        notify_review_items: bool = False,
        gemini_fallback: GeminiFallbackService | None = None,
        gemini_text_analysis: GeminiTextAnalysisService | None = None,
        structured_evaluator: StructuredEligibilityEvaluator | None = None,
    ) -> None:
        super().__init__(
            collector,
            repository,
            notifier,
            include_keywords,
            summary_batch_size,
            detail_fetcher,
            evaluator,
            profile,
            notify_review_items,
            gemini_fallback,
            gemini_text_analysis,
            structured_evaluator,
        )

    def _personalization_enabled(self) -> bool:
        return True

    def _evaluate_fetch_result(
        self,
        item: Scholarship,
        fetch_result: DetailFetchResult,
    ) -> tuple[EligibilityDecision, str, str, GeminiAnalysisDiagnostic | None]:
        """以 rules_status 傳遞附件狀態，不在文字中插入附件 marker。"""
        if fetch_result.source.status == "error":
            decision = EligibilityDecision(REVIEW, ("公告正文讀取失敗，暫不推播。",))
            return decision, UNKNOWN, "", None

        decision, notice_kind, detail_text = self._evaluate_detail(
            item,
            fetch_result.text,
            fetch_result.rules_status,
        )
        if notice_kind != APPLICATION or decision.status != REVIEW or not self.gemini_fallback:
            return decision, notice_kind, detail_text, None

        fallback = self.gemini_fallback.analyze(item.title, fetch_result)
        if fallback is None or not fallback.rule_text:
            diagnostic = fallback.diagnostic if fallback else None
            return decision, notice_kind, detail_text, diagnostic

        resolved_text = _merge_gemini_rules_without_attachment_markers(
            detail_text,
            fallback.rule_text,
        )
        rules_status = (
            RULES_STATUS_RESOLVED
            if fallback.diagnostic.status in {"success", "cache"}
            else fetch_result.rules_status
        )
        evaluator = self.evaluator
        profile = self.profile
        assert evaluator is not None
        assert profile is not None
        decision = evaluator.evaluate(
            item,
            resolved_text,
            profile,
            rules_status=rules_status,
        )
        return decision, notice_kind, resolved_text, fallback.diagnostic


def _merge_gemini_rules_without_attachment_markers(
    detail_text: str,
    rule_text: str,
) -> str:
    cleaned_rules = rule_text.replace(UNRESOLVED_ATTACHMENT_MARKER, "")
    return f"{detail_text}\n【Gemini資格抽取】\n{cleaned_rules}"
