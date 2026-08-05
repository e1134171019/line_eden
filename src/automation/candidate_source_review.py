# -*- coding: utf-8 -*-

import ast
from dataclasses import asdict, dataclass
import json
import os
import subprocess

from config import HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT
from src.catalogs.additional_source_catalog import ADDITIONAL_SCHOLARSHIP_SOURCES
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
)
from src.collectors.collection_diagnostics import CollectionMode

CATALOG_PATH = "src/catalogs/additional_source_catalog.py"


@dataclass(frozen=True)
class CandidateReviewResult:
    source_id: str
    display_name: str
    status: str
    parsed_count: int
    pages_succeeded: int
    error: str
    review_reason: str


def _source_ids_from_python(content: str) -> set[str]:
    """從來源目錄語法樹擷取明確宣告的 source_id。"""

    tree = ast.parse(content)
    source_ids: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "source_id":
                continue
            value = keyword.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                source_ids.add(value.value)
    return source_ids


def _base_source_ids(base_ref: str) -> set[str]:
    """讀取PR基準版本目錄，找出本次真正新增的來源。"""

    result = subprocess.run(
        ["git", "show", f"{base_ref}:{CATALOG_PATH}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return _source_ids_from_python(result.stdout)


def _review_source(source: object) -> CandidateReviewResult:
    collector = AdditionalScholarshipSourceCollector(
        source,  # type: ignore[arg-type]
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        CollectionMode.INCREMENTAL,
        1,
    )
    try:
        records = collector.collect()
    except Exception as error:  # noqa: BLE001 - 來源錯誤必須轉成審查結果
        return CandidateReviewResult(
            source_id=str(getattr(source, "source_id")),
            display_name=str(getattr(source, "display_name")),
            status="failed",
            parsed_count=0,
            pages_succeeded=collector.diagnostic.pages_succeeded,
            error=str(error),
            review_reason=str(getattr(source, "review_reason")),
        )

    return CandidateReviewResult(
        source_id=str(getattr(source, "source_id")),
        display_name=str(getattr(source, "display_name")),
        status="accepted" if records else "rejected_empty",
        parsed_count=len(records),
        pages_succeeded=collector.diagnostic.pages_succeeded,
        error=collector.diagnostic.error,
        review_reason=str(getattr(source, "review_reason")),
    )


def main() -> None:
    base_ref = os.getenv("SOURCE_REVIEW_BASE_REF", "").strip()
    if not base_ref:
        raise SystemExit("缺少 SOURCE_REVIEW_BASE_REF，無法識別本次新增來源。")

    base_ids = _base_source_ids(base_ref)
    candidates = tuple(
        source
        for source in ADDITIONAL_SCHOLARSHIP_SOURCES
        if source.source_id not in base_ids
    )
    if not candidates:
        print("本次PR沒有新增來源，略過候選來源審查。")
        return

    results = tuple(_review_source(source) for source in candidates)
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
