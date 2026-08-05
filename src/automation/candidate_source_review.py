# -*- coding: utf-8 -*-

from dataclasses import asdict, dataclass
import json

from config import HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT
from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalScholarshipSource,
)
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
)
from src.collectors.collection_diagnostics import CollectionMode


@dataclass(frozen=True)
class CandidateReviewResult:
    source_id: str
    display_name: str
    status: str
    parsed_count: int
    pages_succeeded: int
    health_error: str
    review_reason: str


def review_candidate(source: AdditionalScholarshipSource) -> CandidateReviewResult:
    """以每日增量條件測試單一候選來源，零筆或錯誤都不准加入。"""

    collector = AdditionalScholarshipSourceCollector(
        source,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        CollectionMode.INCREMENTAL,
        1,
    )
    try:
        records = collector.collect()
    except Exception as error:  # noqa: BLE001 - 必須把來源錯誤轉成審查結果
        return CandidateReviewResult(
            source_id=source.source_id,
            display_name=source.display_name,
            status="failed",
            parsed_count=0,
            pages_succeeded=collector.diagnostic.pages_succeeded,
            health_error=str(error),
            review_reason=source.review_reason,
        )

    status = "accepted" if records else "rejected_empty"
    return CandidateReviewResult(
        source_id=source.source_id,
        display_name=source.display_name,
        status=status,
        parsed_count=len(records),
        pages_succeeded=collector.diagnostic.pages_succeeded,
        health_error=collector.diagnostic.error,
        review_reason=source.review_reason,
    )


def main() -> None:
    candidates = tuple(
        source
        for source in ADDITIONAL_SCHOLARSHIP_SOURCES
        if source.review_reason.strip()
    )
    if not candidates:
        raise SystemExit("沒有標記 review_reason 的候選來源。")

    results = tuple(review_candidate(source) for source in candidates)
    print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))

    rejected = [result for result in results if result.status != "accepted"]
    if rejected:
        details = ", ".join(
            f"{result.display_name}({result.status})" for result in rejected
        )
        raise SystemExit(f"候選來源未通過審查：{details}")

    print(f"候選來源審查通過：{len(results)} 個。")


if __name__ == "__main__":
    main()
