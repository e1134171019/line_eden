# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import Enum


class RunMode(str, Enum):
    """Scholarship Agent 可執行的互斥模式。"""

    LIVE = "live"
    DRY_RUN = "dry_run"
    AUDIT = "audit"
    INITIALIZE_BASELINE = "initialize_baseline"


@dataclass(frozen=True)
class CliOptions:
    """已解析且型別安全的命令列選項。"""

    mode: RunMode
    use_gemini: bool = False
