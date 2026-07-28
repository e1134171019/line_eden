# -*- coding: utf-8 -*-

from enum import Enum


class RunMode(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    AUDIT = "audit"
    INITIALIZE_BASELINE = "initialize_baseline"

    @property
    def is_live(self) -> bool:
        return self is RunMode.LIVE

    @property
    def requires_profile(self) -> bool:
        return self is not RunMode.INITIALIZE_BASELINE
