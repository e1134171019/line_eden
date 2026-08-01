# -*- coding: utf-8 -*-

from typing import Protocol, runtime_checkable

from src.models.scholarship import Scholarship


@runtime_checkable
class BaseCollector(Protocol):
    """以結構化型別定義可插拔公告來源介面。"""

    # 定義統一的公告蒐集介面。
    def collect(self) -> list[Scholarship]: ...


@runtime_checkable
class CoreEvidenceAwareCollector(Protocol):
    """需要前序核心來源公告來驗證涵蓋方案的 Collector。"""

    def load_core_evidence(self, notices: tuple[Scholarship, ...]) -> None: ...


@runtime_checkable
class TargetRecordAwareCollector(Protocol):
    """可將聚合來源輸出明確對應回單一邏輯監測目標。"""

    def target_id_for(self, notice: Scholarship) -> str: ...
