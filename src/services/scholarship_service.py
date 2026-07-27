# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Callable

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.base_collector import BaseCollector
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityDecision,
    EligibilityEvaluator,
)
from src.formatters.scholarship_message_formatter import (
    build_summary_message,
    split_scholarships,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository


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


class ScholarshipService:
    """協調蒐集、個人資格判斷與 LINE 摘要通知流程。"""

    # 注入蒐集器、資料庫、通知器與個人化評估元件。
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

    # 執行蒐集、資格判斷與通知流程。
    def run(self, dry_run: bool) -> ServiceResult:
        collected = self._collect_and_discover()
        pending_items, counts = self._prepare_notifiable_items()
        if dry_run:
            return self._build_dry_run_result(collected, pending_items, counts)
        return self._run_live_mode(collected, pending_items, counts)

    # 執行首次基準化，不推播且不需要個人背景。
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

    # 蒐集公告並寫入 discovered 資料。
    def _collect_and_discover(self) -> list[Scholarship]:
        collected = self._filter_collected(self.collector.collect())
        self.repository.discover(collected)
        return collected

    # 依標題關鍵字過濾非獎助學金公告。
    def _filter_collected(self, collected: list[Scholarship]) -> list[Scholarship]:
        if not self.include_keywords:
            return collected
        return [
            item
            for item in collected
            if any(keyword in item.title for keyword in self.include_keywords)
        ]

    # 評估尚未用目前背景判斷的公告並回傳可通知資料。
    def _prepare_notifiable_items(
        self,
    ) -> tuple[list[Scholarship], tuple[int, int, int]]:
        if not self._personalization_enabled():
            pending = self.repository.list_pending()
            return pending, (len(pending), 0, 0)
        profile_hash = self.profile.fingerprint()
        self._evaluate_pending(profile_hash)
        items = self.repository.list_notifiable(profile_hash, self.notify_review_items)
        counts = self._eligibility_counts(profile_hash)
        return items, counts

    # 確認個人化資格判斷元件是否完整注入。
    def _personalization_enabled(self) -> bool:
        return all((self.detail_fetcher, self.evaluator, self.profile))

    # 逐筆讀取公告內頁並保存資格判斷。
    def _evaluate_pending(self, profile_hash: str) -> None:
        for item in self.repository.list_for_evaluation(profile_hash):
            decision = self._evaluate_item(item)
            self.repository.mark_eligibility(
                item.content_hash,
                decision.status,
                decision.reason_text(),
                profile_hash,
            )

    # 評估單筆公告，內頁讀取失敗時採保守不推播。
    def _evaluate_item(self, item: Scholarship) -> EligibilityDecision:
        try:
            detail_text = self.detail_fetcher.fetch_text(item)
        except Exception:
            return EligibilityDecision(REVIEW, ("公告內文讀取失敗，暫不推播。",))
        return self.evaluator.evaluate(item, detail_text, self.profile)

    # 統計目前背景下各資格狀態的公告數量。
    def _eligibility_counts(self, profile_hash: str) -> tuple[int, int, int]:
        eligible = self.repository.count_eligibility(profile_hash, ELIGIBLE)
        review = self.repository.count_eligibility(profile_hash, REVIEW)
        ineligible = self.repository.count_eligibility(profile_hash, INELIGIBLE)
        return eligible, review, ineligible

    # 建立 dry-run 結果，不呼叫 LINE。
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
        )

    # 正式模式只推播個人化判斷後的可通知公告。
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
            )
        return self._notify_batches(collected, pending_items, counts)

    # 分批推播摘要，成功後才標記該批公告為已通知。
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
        )

    # 逐批送出摘要並更新成功批次的 notified_at。
    def _send_batches(self, batches: list[list[Scholarship]]) -> int:
        notified_count = 0
        for index, batch in enumerate(batches, start=1):
            message = build_summary_message(batch, index, len(batches))
            self.notifier(message)
            hashes = [item.content_hash for item in batch]
            notified_count += self.repository.mark_notified(hashes)
        return notified_count
