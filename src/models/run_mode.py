# -*- coding: utf-8 -*-

from argparse import Namespace
from enum import Enum


class RunMode(str, Enum):
    """命令列執行模式；每個模式明確描述是否允許傳送 LINE。"""

    LIVE = "live"
    DRY_RUN = "dry_run"
    AUDIT = "audit"
    INITIALIZE_BASELINE = "initialize_baseline"

    @property
    def sends_line(self) -> bool:
        return self is RunMode.LIVE


def resolve_run_mode(args: Namespace) -> RunMode:
    """將互斥命令列旗標轉成單一明確模式。"""
    if args.initialize_baseline:
        return RunMode.INITIALIZE_BASELINE
    if args.audit:
        return RunMode.AUDIT
    if args.dry_run:
        return RunMode.DRY_RUN
    return RunMode.LIVE
