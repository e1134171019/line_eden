# -*- coding: utf-8 -*-

import main
from src.collectors.collection_diagnostics import CollectionMode
from src.runtime.run_mode import RunMode


# 稽核與初始化必須抓完整歷史；正式與 dry-run 僅抓最新頁。
def test_run_mode_maps_to_collection_mode() -> None:
    assert main._collection_mode(RunMode.AUDIT) is CollectionMode.FULL_AUDIT
    assert (
        main._collection_mode(RunMode.INITIALIZE_BASELINE)
        is CollectionMode.FULL_AUDIT
    )
    assert main._collection_mode(RunMode.DAILY) is CollectionMode.INCREMENTAL
    assert main._collection_mode(RunMode.LIVE) is CollectionMode.INCREMENTAL
    assert main._collection_mode(RunMode.DRY_RUN) is CollectionMode.INCREMENTAL
