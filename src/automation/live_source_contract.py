# -*- coding: utf-8 -*-

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from config import (
    BASE_DIR,
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    SOURCE_MAX_PAGES,
    TUN_FETCH_WORKERS,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.decision_safe_tun_program_watch_collector import (
    DecisionSafeTunProgramWatchCollector,
)
from src.collectors.tun_program_watch_collector import ProgramSourceState

ARTIFACT_DIR = BASE_DIR / "artifacts"
JSON_PATH = ARTIFACT_DIR / "live-source-contract.json"
MARKDOWN_PATH = ARTIFACT_DIR / "live-source-contract.md"
ACCEPTED_SOURCE_STATUSES = frozenset({"matched", "no_current_announcement"})


@dataclass(frozen=True)
class LiveSourceContractResult:
    """38 項真實來源執行結果與合併門檻。"""

    states: tuple[ProgramSourceState, ...]
    accepted_count: int
    failed_program_ids: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failed_program_ids and len(self.states) == 38


def evaluate_source_states(
    states: Iterable[ProgramSourceState],
) -> LiveSourceContractResult:
    items = tuple(states)
    failed = tuple(
        item.program_id
        for item in items
        if item.status not in ACCEPTED_SOURCE_STATUSES
    )
    return LiveSourceContractResult(items, len(items) - len(failed), failed)


def write_json_report(result: LiveSourceContractResult, path: Path = JSON_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed": result.passed,
        "total": len(result.states),
        "accepted": result.accepted_count,
        "failed_program_ids": list(result.failed_program_ids),
        "accepted_statuses": sorted(ACCEPTED_SOURCE_STATUSES),
        "programs": [asdict(item) for item in result.states],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_markdown_report(
    result: LiveSourceContractResult,
    path: Path = MARKDOWN_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 38 項來源 Live Contract",
        "",
        f"- 驗收結果：{'PASS' if result.passed else 'FAIL'}",
        f"- 通過：{result.accepted_count} / {len(result.states)}",
        f"- 失敗：{len(result.failed_program_ids)}",
        "",
        "| program_id | status | candidates | score | entry_url | reason |",
        "|---|---:|---:|---:|---|---|",
    ]
    lines.extend(_state_markdown_line(item) for item in result.states)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _state_markdown_line(item: ProgramSourceState) -> str:
    values = (
        item.program_id,
        item.status,
        str(item.candidate_count),
        str(item.top_score),
        item.entry_url,
        item.reason,
    )
    escaped = tuple(value.replace("|", "\\|").replace("\n", " ") for value in values)
    return "| " + " | ".join(escaped) + " |"


def run_live_source_contract() -> LiveSourceContractResult:
    collector = DecisionSafeTunProgramWatchCollector(
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        CollectionMode.FULL_AUDIT,
        SOURCE_MAX_PAGES,
        TUN_FETCH_WORKERS,
    )
    collector.collect()
    result = evaluate_source_states(collector.program_states)
    write_json_report(result)
    write_markdown_report(result)
    print(MARKDOWN_PATH.read_text(encoding="utf-8"))
    return result


def main() -> int:
    result = run_live_source_contract()
    if result.passed:
        return 0
    print("Live source contract 未通過：" + ", ".join(result.failed_program_ids))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
