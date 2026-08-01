# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata

from config import SOURCE_TARGET_ANOMALY_LIMIT, SOURCE_VALIDATION_EXAMPLE_LIMIT
from src.collectors.base_collector import (
    BaseCollector,
    CoreEvidenceAwareCollector,
    TargetRecordAwareCollector,
)
from src.collectors.collection_diagnostics import (
    AccountingStatus,
    CollectorDiagnostic,
    RejectionReasonCount,
    RowAccounting,
    SourceAccessMode,
    SourceTargetDiagnostic,
    build_row_accounting,
)
from src.models.scholarship import Scholarship

_GENERIC_TITLES = {
    "獎學金",
    "助學金",
    "獎助學金",
    "獎學金公告",
    "助學金公告",
    "獎助學金公告",
    "申請公告",
}
_COMPLETENESS_LABELS = {
    "complete": "完整",
    "partial": "部分完成",
    "incremental": "增量",
    "failed": "失敗",
    "unknown": "完整性未知",
}


@dataclass(frozen=True)
class CollectorFailure:
    source: str
    error: str


@dataclass(frozen=True)
class CrossSourceDuplicate:
    """保存被跨來源合併的公告及其主顯示公告。"""

    duplicate_key: str
    canonical: Scholarship
    duplicate: Scholarship


@dataclass(frozen=True)
class DuplicateIdentityGroup:
    """保存同一 Collector 中共用 announcement identity 的公告。"""

    announcement_id: str
    notices: tuple[Scholarship, ...]


class SourceValidationStatus(StrEnum):
    """區分來源輸出是否通過去重前資料契約。"""

    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class SourceValidation:
    """保存來源輸出的去重前驗證結果。"""

    status: SourceValidationStatus
    errors: tuple[str, ...]
    row_accounting: RowAccounting


@dataclass(frozen=True)
class SourceDiagnostic:
    source: str
    status: str
    collected_count: int
    accepted_count: int
    duplicate_count: int
    error: str = ""
    completeness: str = "unknown"
    pages_detected: int | None = None
    pages_requested: int = 0
    pages_succeeded: int = 0
    raw_rows: int = 0
    parsed_rows: int = 0
    rejected_rows: int = 0
    rejection_reasons: tuple[RejectionReasonCount, ...] = tuple()
    stop_reason: str = ""
    ssl_compatibility_fallback: bool = False
    child_sources_detected: int = 0
    child_sources_succeeded: int = 0
    target_diagnostics: tuple[SourceTargetDiagnostic, ...] = tuple()
    row_accounting: RowAccounting = RowAccounting()
    validation: SourceValidation | None = None


class MultiSourceCollector(BaseCollector):
    """依序執行多個來源，隔離單站錯誤並輸出可稽核完整性。"""

    def __init__(self, collectors: list[BaseCollector]) -> None:
        if not collectors:
            raise ValueError("MultiSourceCollector 至少需要一個來源。")
        self.collectors = collectors
        self.failures: list[CollectorFailure] = []
        self.diagnostics: list[SourceDiagnostic] = []
        self.source_records: tuple[Scholarship, ...] = tuple()
        self.duplicate_records: tuple[CrossSourceDuplicate, ...] = tuple()
        self.quarantined_records: tuple[Scholarship, ...] = tuple()

    # 執行所有來源並跨站去重。
    def collect(self) -> list[Scholarship]:
        self.failures = []
        self.diagnostics = []
        records: list[Scholarship] = []
        source_records: list[Scholarship] = []
        canonical_by_key: dict[str, Scholarship] = {}
        duplicate_records: list[CrossSourceDuplicate] = []
        quarantined_records: list[Scholarship] = []
        successful_sources = 0
        for collector in self.collectors:
            source = _collector_label(collector)
            if isinstance(collector, CoreEvidenceAwareCollector):
                collector.load_core_evidence(tuple(source_records))
            try:
                collected = collector.collect()
            except Exception as error:
                self._record_failure(source, collector, error)
                continue
            source_records.extend(collected)
            detail = _collector_diagnostic(collector)
            supports_target_isolation = isinstance(
                collector,
                TargetRecordAwareCollector,
            )
            validation = validate_source_collection(
                detail,
                collected,
                allow_target_failures=supports_target_isolation,
            )
            if validation.status is SourceValidationStatus.INVALID:
                quarantined_records.extend(collected)
                self._record_validation_failure(
                    source,
                    collector,
                    collected,
                    validation,
                )
                continue
            accepted_records, target_quarantine = _partition_target_records(
                collector,
                detail,
                collected,
            )
            quarantined_records.extend(target_quarantine)
            successful_sources += 1
            accepted, duplicates = self._append_unique(
                records,
                canonical_by_key,
                duplicate_records,
                accepted_records,
            )
            self.diagnostics.append(
                self._build_diagnostic(
                    source,
                    collector,
                    collected,
                    accepted,
                    duplicates,
                    validation,
                )
            )
        self.source_records = tuple(source_records)
        self.duplicate_records = tuple(duplicate_records)
        self.quarantined_records = tuple(quarantined_records)
        self._validate_collection(successful_sources, records)
        return records

    # 將來源數、公告數與完整性分開呈現。
    def summary_lines(self) -> list[str]:
        lines = [
            self._health_line(),
            self._target_health_line(),
            self._cross_source_conservation_line(),
        ]
        for item in self.diagnostics:
            if item.status == "error":
                if item.validation and item.validation.status is SourceValidationStatus.INVALID:
                    lines.append(
                        f"{item.source}：驗證失敗，隔離 {item.collected_count} 筆（{item.error}）"
                    )
                else:
                    lines.append(f"{item.source}：失敗（{item.error}）")
                lines.extend(_target_anomaly_lines(item))
                continue
            if item.status == "empty":
                lines.append(f"{item.source}：可連線，但解析 0 筆")
                lines.extend(_target_anomaly_lines(item))
                continue
            lines.append(self._source_line(item))
            lines.extend(_accounting_anomaly_lines(item))
            lines.extend(_target_anomaly_lines(item))
        return lines

    # 合併 collector 自身診斷與跨站去重結果。
    def _build_diagnostic(
        self,
        source: str,
        collector: BaseCollector,
        collected: list[Scholarship],
        accepted: int,
        duplicates: int,
        validation: SourceValidation,
    ) -> SourceDiagnostic:
        detail = _collector_diagnostic(collector)
        status = "empty" if not collected else "success"
        if detail.completeness == "partial" and collected:
            status = "partial"
        return SourceDiagnostic(
            source=source,
            status=status,
            collected_count=len(collected),
            accepted_count=accepted,
            duplicate_count=duplicates,
            error=detail.error,
            completeness=detail.completeness,
            pages_detected=detail.pages_detected,
            pages_requested=detail.pages_requested,
            pages_succeeded=detail.pages_succeeded,
            raw_rows=detail.raw_rows,
            parsed_rows=detail.parsed_rows,
            rejected_rows=detail.rejected_rows,
            rejection_reasons=detail.rejection_reasons,
            stop_reason=detail.stop_reason,
            ssl_compatibility_fallback=detail.ssl_compatibility_fallback,
            child_sources_detected=detail.child_sources_detected,
            child_sources_succeeded=detail.child_sources_succeeded,
            target_diagnostics=_target_diagnostics(source, collector, detail),
            row_accounting=build_row_accounting(detail, len(collected)),
            validation=validation,
        )

    # 將未通過資料契約的來源隔離，不讓它進入跨來源去重與通知。
    def _record_validation_failure(
        self,
        source: str,
        collector: BaseCollector,
        collected: list[Scholarship],
        validation: SourceValidation,
    ) -> None:
        message = "；".join(validation.errors)
        detail = _collector_diagnostic(collector)
        self.failures.append(CollectorFailure(source, message))
        self.diagnostics.append(
            SourceDiagnostic(
                source=source,
                status="error",
                collected_count=len(collected),
                accepted_count=0,
                duplicate_count=0,
                error=message,
                completeness="failed",
                pages_detected=detail.pages_detected,
                pages_requested=detail.pages_requested,
                pages_succeeded=detail.pages_succeeded,
                raw_rows=detail.raw_rows,
                parsed_rows=detail.parsed_rows,
                rejected_rows=detail.rejected_rows,
                rejection_reasons=detail.rejection_reasons,
                stop_reason="source_contract_failed",
                child_sources_detected=detail.child_sources_detected,
                child_sources_succeeded=detail.child_sources_succeeded,
                target_diagnostics=_target_diagnostics(source, collector, detail),
                row_accounting=validation.row_accounting,
                validation=validation,
            )
        )

    # 記錄單一來源錯誤，不讓例外中斷其餘來源。
    def _record_failure(
        self,
        source: str,
        collector: BaseCollector,
        error: Exception,
    ) -> None:
        message = _safe_error(error)
        detail = _collector_diagnostic(collector)
        self.failures.append(CollectorFailure(source, message))
        self.diagnostics.append(
            SourceDiagnostic(
                source,
                "error",
                0,
                0,
                0,
                message,
                completeness="failed",
                pages_detected=detail.pages_detected,
                pages_requested=detail.pages_requested,
                pages_succeeded=detail.pages_succeeded,
                raw_rows=detail.raw_rows,
                parsed_rows=detail.parsed_rows,
                rejected_rows=detail.rejected_rows,
                rejection_reasons=detail.rejection_reasons,
                stop_reason=detail.stop_reason,
                ssl_compatibility_fallback=detail.ssl_compatibility_fallback,
                child_sources_detected=detail.child_sources_detected,
                child_sources_succeeded=detail.child_sources_succeeded,
                target_diagnostics=_target_diagnostics(source, collector, detail),
                row_accounting=build_row_accounting(detail, 0),
            )
        )

    # 將單一來源結果跨站去重後加入總清單。
    def _append_unique(
        self,
        records: list[Scholarship],
        canonical_by_key: dict[str, Scholarship],
        duplicate_records: list[CrossSourceDuplicate],
        collected: list[Scholarship],
    ) -> tuple[int, int]:
        accepted = 0
        duplicates = 0
        for item in collected:
            key = build_cross_source_key(item)
            canonical = canonical_by_key.get(key)
            if canonical is not None:
                duplicate_records.append(CrossSourceDuplicate(key, canonical, item))
                duplicates += 1
                continue
            canonical_by_key[key] = item
            records.append(item)
            accepted += 1
        return accepted, duplicates

    # 來源全部失敗或全部空結果時採 fail closed。
    def _validate_collection(
        self,
        successful_sources: int,
        records: list[Scholarship],
    ) -> None:
        if successful_sources == 0:
            details = "; ".join(
                f"{failure.source}: {failure.error}" for failure in self.failures
            )
            raise RuntimeError(f"五個官方來源全部失敗：{details}")
        if not records:
            raise RuntimeError("官方來源可連線，但沒有解析到任何獎助學金公告。")

    # 彙整設定來源、產出資料來源、空結果、部分完成與失敗數量。
    def _health_line(self) -> str:
        configured = len(self.collectors)
        producing = sum(item.status in {"success", "partial"} for item in self.diagnostics)
        empty = sum(item.status == "empty" for item in self.diagnostics)
        partial = sum(item.status == "partial" for item in self.diagnostics)
        failed = sum(item.status == "error" for item in self.diagnostics)
        health = "正常" if producing == configured and partial == 0 else "降級"
        return (
            f"頂層來源群組：設定 {configured}，成功產生資料 {producing}，"
            f"空結果 {empty}，部分完成 {partial}，失敗 {failed}；整體：{health}"
        )

    # 將邏輯目標、直接監測、核心涵蓋及唯一入口分開計數。
    def _target_health_line(self) -> str:
        targets = tuple(
            target
            for diagnostic in self.diagnostics
            for target in diagnostic.target_diagnostics
        )
        direct = sum(
            target.access_mode is SourceAccessMode.DIRECT for target in targets
        )
        covered = sum(
            target.access_mode is SourceAccessMode.CORE_COVERED for target in targets
        )
        pending = sum(
            target.access_mode is SourceAccessMode.PENDING for target in targets
        )
        urls = {target.entry_url for target in targets if target.entry_url}
        domains = {target.domain for target in targets if target.domain}
        return (
            f"監測目標：邏輯 {len(targets)}，直接 {direct}，核心涵蓋 {covered}，"
            f"待確認 {pending}；唯一入口 URL {len(urls)}，唯一網域 {len(domains)}"
        )

    # 顯示跨來源去重前後仍可回查的資料守恆關係。
    def _cross_source_conservation_line(self) -> str:
        retained = (
            len(self.source_records)
            - len(self.duplicate_records)
            - len(self.quarantined_records)
        )
        return (
            f"跨來源資料守恆：來源輸出 {len(self.source_records)} = "
            f"保留 {retained} + 重複關聯 {len(self.duplicate_records)} + "
            f"驗證隔離 {len(self.quarantined_records)}"
        )

    # 建立單一來源的人類可讀完整性摘要。
    def _source_line(self, item: SourceDiagnostic) -> str:
        parts = [f"{item.source}：{_COMPLETENESS_LABELS.get(item.completeness, item.completeness)}"]
        if item.pages_detected is not None and item.pages_requested:
            parts.append(f"頁面 {item.pages_succeeded}/{item.pages_detected}")
        if item.child_sources_detected:
            target_parts = _target_count_parts(item.target_diagnostics)
            parts.append(
                f"監測目標 {item.child_sources_succeeded}/{item.child_sources_detected}"
                f"（{'、'.join(target_parts)}）"
            )
        if item.raw_rows:
            row_parts = [f"原始列 {item.raw_rows}", f"解析 {item.parsed_rows}"]
            if item.row_accounting.duplicate_rows:
                row_parts.append(f"來源內去重 {item.row_accounting.duplicate_rows}")
            row_parts.append(f"排除 {item.rejected_rows}")
            if item.rejection_reasons:
                reasons = "、".join(
                    f"{reason.reason} {reason.count}"
                    for reason in item.rejection_reasons
                )
                row_parts.append(f"原因：{reasons}")
            parts.append("，".join(row_parts))
        parts.append(f"跨來源去重後保留 {item.accepted_count}/{item.collected_count} 筆")
        if item.ssl_compatibility_fallback:
            parts.append("SSL 相容重試")
        if item.stop_reason:
            parts.append(f"停止：{item.stop_reason}")
        return "；".join(parts)


def validate_source_collection(
    diagnostic: CollectorDiagnostic,
    collected: list[Scholarship],
    allow_target_failures: bool = False,
) -> SourceValidation:
    """純函式：確認來源資料符合去重前的最低契約。"""

    accounting = build_row_accounting(diagnostic, len(collected))
    errors = _accounting_errors(accounting)
    invalid_rows = sum(not _has_required_fields(notice) for notice in collected)
    if invalid_rows:
        errors.append(f"{invalid_rows} 筆公告缺少來源、標題、網址或 identity")
    duplicate_groups = find_duplicate_identity_groups(collected)
    duplicate_identities = sum(len(group.notices) - 1 for group in duplicate_groups)
    if duplicate_identities:
        samples = "；".join(
            _duplicate_identity_sample(group)
            for group in duplicate_groups[:SOURCE_VALIDATION_EXAMPLE_LIMIT]
        )
        errors.append(
            f"Collector 輸出內有 {duplicate_identities} 筆重複 identity；樣本：{samples}"
        )
    errors.extend(_completeness_errors(diagnostic, allow_target_failures))
    errors.extend(_rejection_reason_errors(diagnostic))
    status = SourceValidationStatus.INVALID if errors else SourceValidationStatus.VALID
    return SourceValidation(status, tuple(errors), accounting)


def _accounting_errors(accounting: RowAccounting) -> list[str]:
    """純函式：將來源列數帳本狀態轉成驗證錯誤。"""

    if accounting.status is AccountingStatus.UNTRACKED:
        return ["Collector 未提供可驗證的列數診斷"]
    if accounting.status is AccountingStatus.BALANCED:
        return []
    return [
        (
            f"列數不守恆：原始 {accounting.raw_rows}、已說明 "
            f"{accounting.accounted_rows}、解析 {accounting.parsed_rows}、"
            f"輸出 {accounting.emitted_rows}"
        )
    ]


def _rejection_reason_errors(diagnostic: CollectorDiagnostic) -> list[str]:
    """純函式：有啟用原因帳本時，排除數量必須完整守恆。"""

    if not diagnostic.rejection_reasons:
        if diagnostic.rejected_rows and diagnostic.stop_reason.startswith("program_watch"):
            return ["方案監測排除列缺少原因帳本"]
        return []
    if any(reason.count < 1 or not reason.reason.strip() for reason in diagnostic.rejection_reasons):
        return ["排除原因不得為空且數量必須大於零"]
    explained = sum(reason.count for reason in diagnostic.rejection_reasons)
    if explained != diagnostic.rejected_rows:
        return [f"排除原因不守恆：排除 {diagnostic.rejected_rows}、已說明 {explained}"]
    return []


def _has_required_fields(notice: Scholarship) -> bool:
    """純函式：確認公告具有來源、標題、網址與穩定 identity。"""

    return all(
        value.strip()
        for value in (
            notice.source,
            notice.title,
            notice.source_url,
            notice.announcement_id,
        )
    )


def find_duplicate_identity_groups(
    collected: list[Scholarship],
) -> tuple[DuplicateIdentityGroup, ...]:
    """純函式：依公告 identity 建立來源內衝突群組。"""

    grouped: dict[str, list[Scholarship]] = {}
    for notice in collected:
        grouped.setdefault(notice.announcement_id, []).append(notice)
    return tuple(
        DuplicateIdentityGroup(announcement_id, tuple(notices))
        for announcement_id, notices in grouped.items()
        if len(notices) > 1
    )


def _duplicate_identity_sample(group: DuplicateIdentityGroup) -> str:
    """純函式：壓縮一組 identity 衝突供來源報告人工核對。"""

    first = group.notices[0]
    variants = " / ".join(
        f"{notice.published_date}:{notice.title[:36]}" for notice in group.notices[:3]
    )
    return f"{first.source}｜{first.source_url[:100]}｜{variants}"


def _completeness_errors(
    diagnostic: CollectorDiagnostic,
    allow_target_failures: bool = False,
) -> list[str]:
    """純函式：驗證宣告完整的來源確實抓完頁面與子來源。"""

    errors: list[str] = []
    if (
        diagnostic.completeness == "complete"
        and diagnostic.pages_detected is not None
        and diagnostic.pages_succeeded != diagnostic.pages_detected
    ):
        errors.append("宣告完整但沒有抓完所有偵測頁面")
    if (
        diagnostic.completeness == "complete"
        and diagnostic.child_sources_detected
        and diagnostic.child_sources_succeeded != diagnostic.child_sources_detected
    ):
        errors.append("宣告完整但沒有完成所有子來源")
    failed_targets = tuple(
        target
        for target in diagnostic.target_diagnostics
        if target.access_mode in {
            SourceAccessMode.DIRECT,
            SourceAccessMode.CORE_COVERED,
        }
        and not target.is_succeeded
    )
    is_incremental_watch = diagnostic.stop_reason.startswith("program_watch_incremental")
    if failed_targets and not is_incremental_watch and not allow_target_failures:
        samples = "、".join(target.display_name for target in failed_targets[:5])
        errors.append(
            f"{len(failed_targets)} 個監測方案未通過語意驗證：{samples}"
        )
    return errors


def _partition_target_records(
    collector: BaseCollector,
    diagnostic: CollectorDiagnostic,
    collected: list[Scholarship],
) -> tuple[list[Scholarship], list[Scholarship]]:
    """純函式：只隔離失敗目標自己的公告，避免聚合來源整組連坐。"""

    if not isinstance(collector, TargetRecordAwareCollector):
        return collected, []
    failed_target_ids = {
        target.target_id
        for target in diagnostic.target_diagnostics
        if target.access_mode in {
            SourceAccessMode.DIRECT,
            SourceAccessMode.CORE_COVERED,
        }
        and not target.is_succeeded
    }
    accepted: list[Scholarship] = []
    quarantined: list[Scholarship] = []
    for notice in collected:
        destination = (
            quarantined
            if collector.target_id_for(notice) in failed_target_ids
            else accepted
        )
        destination.append(notice)
    return accepted, quarantined


def build_cross_source_key(item: Scholarship) -> str:
    """純函式：同名公告只在相同申請年度內合併。"""

    title = _normalize_title(item.title)
    if title in _GENERIC_TITLES:
        return f"{title}|{item.published_date.strip()}"
    return f"{title}|{_notice_cycle_year(item)}"


def _notice_cycle_year(item: Scholarship) -> str:
    """純函式：優先使用日期年度，缺少日期時再從標題擷取年度。"""

    date_year = re.match(r"^(20\d{2})", item.published_date.strip())
    if date_year:
        return date_year.group(1)
    gregorian = re.search(r"(?<!\d)(20\d{2})(?:年度|年)?", item.title)
    if gregorian:
        return gregorian.group(1)
    roc = re.search(r"(?<!\d)(1\d{2})(?:年度|學年度|年)", item.title)
    return str(int(roc.group(1)) + 1911) if roc else "undated"


def _normalize_title(title: str) -> str:
    value = unicodedata.normalize("NFKC", " ".join(title.split())).casefold()
    value = re.sub(r"^[【〖\[][^】〗\]]{1,24}[】〗\]]\s*", "", value)
    value = re.sub(
        r"^(?:轉知|公告|重要資訊|最新消息|有關|函轉|教育部公告)+[：:－\-｜|\s]*",
        "",
        value,
    )
    return re.sub(r"[\W_]+", "", value)


def _collector_label(collector: BaseCollector) -> str:
    label = getattr(collector, "source_label", "")
    if isinstance(label, str) and label.strip():
        return label.strip()
    config = getattr(collector, "config", None)
    display_name = getattr(config, "display_name", "")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    source_name = getattr(config, "source_name", "")
    if isinstance(source_name, str) and source_name.strip():
        return source_name.strip()
    return type(collector).__name__


def _collector_diagnostic(collector: BaseCollector) -> CollectorDiagnostic:
    value = getattr(collector, "diagnostic", None)
    return value if isinstance(value, CollectorDiagnostic) else CollectorDiagnostic()


def _target_diagnostics(
    source: str,
    collector: BaseCollector,
    diagnostic: CollectorDiagnostic,
) -> tuple[SourceTargetDiagnostic, ...]:
    """純函式：聚合來源保留子目標，單站來源建立一個直接目標。"""

    if diagnostic.target_diagnostics:
        return diagnostic.target_diagnostics
    entry_url = _collector_entry_url(collector)
    return (
        SourceTargetDiagnostic(
            target_id=_collector_target_id(collector),
            display_name=source,
            access_mode=SourceAccessMode.DIRECT,
            entry_url=entry_url,
            completeness=diagnostic.completeness,
            pages_detected=diagnostic.pages_detected,
            pages_requested=diagnostic.pages_requested,
            pages_succeeded=diagnostic.pages_succeeded,
            raw_rows=diagnostic.raw_rows,
            parsed_rows=diagnostic.parsed_rows,
            rejected_rows=diagnostic.rejected_rows,
            duplicate_rows=diagnostic.duplicate_rows,
            error=diagnostic.error,
        ),
    )


def _collector_entry_url(collector: BaseCollector) -> str:
    """純函式：取得單站 collector 的設定入口 URL。"""

    source_url = getattr(collector, "source_url", "")
    if isinstance(source_url, str):
        return source_url
    config = getattr(collector, "config", None)
    configured_url = getattr(config, "source_url", "")
    return configured_url if isinstance(configured_url, str) else ""


def _collector_target_id(collector: BaseCollector) -> str:
    """純函式：取得單站來源識別碼。"""

    source_name = getattr(collector, "source_name", "")
    if isinstance(source_name, str) and source_name:
        return source_name
    config = getattr(collector, "config", None)
    configured_name = getattr(config, "source_name", "")
    return configured_name if isinstance(configured_name, str) else type(collector).__name__


def _target_count_parts(
    targets: tuple[SourceTargetDiagnostic, ...],
) -> list[str]:
    """純函式：建立聚合來源的監測口徑摘要。"""

    direct = sum(target.access_mode is SourceAccessMode.DIRECT for target in targets)
    covered = sum(
        target.access_mode is SourceAccessMode.CORE_COVERED for target in targets
    )
    urls = {target.entry_url for target in targets if target.entry_url}
    domains = {target.domain for target in targets if target.domain}
    parts = [f"直接 {direct}"]
    if covered:
        parts.append(f"核心涵蓋 {covered}")
    parts.extend((f"入口 {len(urls)}", f"網域 {len(domains)}"))
    return parts


def _target_anomaly_lines(diagnostic: SourceDiagnostic) -> list[str]:
    """純函式：只展開聚合來源中失敗或部分完成的子目標。"""

    if diagnostic.child_sources_detected == 0:
        return []
    anomalies = [
        target
        for target in diagnostic.target_diagnostics
        if target.access_mode is SourceAccessMode.PENDING
        or target.completeness in {"partial", "failed"}
    ]
    lines = [
        _target_anomaly_line(diagnostic.source, target)
        for target in anomalies[:SOURCE_TARGET_ANOMALY_LIMIT]
    ]
    remaining = len(anomalies) - SOURCE_TARGET_ANOMALY_LIMIT
    if remaining > 0:
        lines.append(f"{diagnostic.source}：另有 {remaining} 個異常監測目標未展開")
    return lines


def _accounting_anomaly_lines(diagnostic: SourceDiagnostic) -> list[str]:
    """純函式：列出來源列數守恆或 collector 輸出契約異常。"""

    accounting = diagnostic.row_accounting
    if accounting.status is not AccountingStatus.UNBALANCED:
        return []
    return [
        (
            f"{diagnostic.source}：資料守恆異常；"
            f"原始 {accounting.raw_rows}，已說明 {accounting.accounted_rows}，"
            f"解析 {accounting.parsed_rows}，實際輸出 {accounting.emitted_rows}，"
            f"未說明差 {accounting.balance_delta}，輸出差 {accounting.emission_delta}"
        )
    ]


def _target_anomaly_line(
    source: str,
    target: SourceTargetDiagnostic,
) -> str:
    """純函式：建立單一異常監測目標的精簡診斷。"""

    parts = [f"{source}／{target.display_name}：{target.completeness}"]
    if target.pages_detected is not None:
        parts.append(f"頁面 {target.pages_succeeded}/{target.pages_detected}")
    if target.error:
        parts.append(f"錯誤：{target.error[:180]}")
    return "；".join(parts)


def _safe_error(error: Exception) -> str:
    text = " ".join(str(error).split())
    return text[:300] or type(error).__name__
