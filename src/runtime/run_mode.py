# -*- coding: utf-8 -*-

from enum import StrEnum


class RunMode(StrEnum):
    """明確描述一次執行的用途與通知權限。"""

    LIVE = "live"
    DAILY = "daily"
    DRY_RUN = "dry_run"
    AUDIT = "audit"
    INITIALIZE_BASELINE = "initialize_baseline"

    @property
    def requires_profile(self) -> bool:
        return self is not RunMode.INITIALIZE_BASELINE

    @property
    def sends_scholarship_notifications(self) -> bool:
        return self in {RunMode.LIVE, RunMode.DAILY}

    @property
    def validates_line_settings(self) -> bool:
        return self in {RunMode.LIVE, RunMode.DAILY}
