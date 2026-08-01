# -*- coding: utf-8 -*-

import main
from src.collectors.collection_diagnostics import CollectionMode
from src.runtime.run_mode import RunMode


# watermark 尚未落地前所有模式都必須完整抓頁，避免排程漏跑造成公告掉到後頁。
def test_run_mode_maps_to_collection_mode() -> None:
    assert main._collection_mode(RunMode.AUDIT) is CollectionMode.FULL_AUDIT
    assert (
        main._collection_mode(RunMode.INITIALIZE_BASELINE)
        is CollectionMode.FULL_AUDIT
    )
    assert main._collection_mode(RunMode.DAILY) is CollectionMode.FULL_AUDIT
    assert main._collection_mode(RunMode.LIVE) is CollectionMode.FULL_AUDIT
    assert main._collection_mode(RunMode.DRY_RUN) is CollectionMode.FULL_AUDIT
