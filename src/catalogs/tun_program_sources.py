# -*- coding: utf-8 -*-

from dataclasses import dataclass, replace

from src.catalogs.tun_2025_program_catalog import (
    OFFICIAL_VERIFIED,
    TUN_2025_PROGRAMS,
    ProgramSourceType,
    ScholarshipProgramWatch,
)

SOURCE_RELAY = "institutional_relay"
SOURCE_CORE = "covered_by_core_source"
SOURCE_PENDING = "pending"


@dataclass(frozen=True)
class ProgramSourceOverride:
    """沒有穩定主辦單位入口時的替代來源契約。"""

    url: str
    status: str
    source_type: ProgramSourceType


# 沒有穩定主辦單位消息列表者，由既有教育部圓夢助學網來源持續探索。
_SOURCE_OVERRIDES: dict[str, ProgramSourceOverride] = {
    program_id: ProgramSourceOverride("", SOURCE_CORE, ProgramSourceType.CORE_COVERED)
    for program_id in (
        "tainan-kaiji",
        "chiu-filial-piety",
        "dapeng-aid",
        "hndasset-wenxiang",
        "harmony-stability",
    )
}


def resolved_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """套用經真實 smoke 與官方資料核對後的來源設定。"""

    resolved: list[ScholarshipProgramWatch] = []
    for item in TUN_2025_PROGRAMS:
        override = _SOURCE_OVERRIDES.get(item.program_id)
        if override is None:
            resolved.append(item)
            continue
        resolved.append(
            replace(
                item,
                official_url=override.url,
                official_status=override.status,
                source_type=override.source_type,
            )
        )
    return tuple(resolved)


def monitorable_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳本群組會直接下載的官方或正式機構轉載入口。"""

    return tuple(
        item
        for item in resolved_programs()
        if item.official_status in {OFFICIAL_VERIFIED, SOURCE_RELAY}
    )


def core_covered_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳已由六核心來源中的教育部圓夢助學網涵蓋的方案。"""

    return tuple(
        item for item in resolved_programs() if item.official_status == SOURCE_CORE
    )


def unresolved_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳仍沒有可靠官方或正式轉載來源的方案。"""

    return tuple(
        item for item in resolved_programs() if item.official_status == SOURCE_PENDING
    )


def validate_resolved_sources() -> None:
    """30 項都必須具有直接監測、核心來源覆蓋或明確待查狀態。"""

    programs = resolved_programs()
    if len(programs) != 30:
        raise ValueError("解析後方案數量必須為 30。")
    for item in programs:
        if item.official_status in {OFFICIAL_VERIFIED, SOURCE_RELAY}:
            if not item.official_url.startswith(("https://", "http://")):
                raise ValueError(f"可監測方案缺少網址：{item.program_id}")
        elif item.official_status == SOURCE_CORE:
            if item.official_url:
                raise ValueError(f"核心來源覆蓋方案不得重複請求：{item.program_id}")
            if item.source_type is not ProgramSourceType.CORE_COVERED:
                raise ValueError(f"核心來源覆蓋方案型態錯誤：{item.program_id}")
        elif item.official_status == SOURCE_PENDING:
            if item.official_url:
                raise ValueError(f"待查方案不得偽造網址：{item.program_id}")
        else:
            raise ValueError(f"未知來源狀態：{item.program_id}")

    _validate_shared_entry_types(programs)


def _validate_shared_entry_types(
    programs: tuple[ScholarshipProgramWatch, ...],
) -> None:
    """純函式：同一入口不可同時宣告不同抓取策略。"""

    types_by_url: dict[str, set[ProgramSourceType]] = {}
    for program in programs:
        if program.official_url:
            types_by_url.setdefault(program.official_url, set()).add(program.source_type)
    conflicted = [url for url, source_types in types_by_url.items() if len(source_types) > 1]
    if conflicted:
        raise ValueError(f"共用入口具有衝突抓取型態：{conflicted[0]}")


validate_resolved_sources()
