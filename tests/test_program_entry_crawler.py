# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import ProgramSourceType
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.program_entry_crawler import select_program_entry_crawler


# 固定頁不可誤追網站導覽列中的頁碼。
def test_fixed_page_crawler_fetches_only_entry() -> None:
    requested: list[str] = []

    def fetch_text(url: str) -> str:
        requested.append(url)
        return '<a href="?page=2">2</a><main>獎學金辦法</main>'

    crawler = select_program_entry_crawler(ProgramSourceType.FIXED_PAGE)
    crawl = crawler.fetch_pages(
        "https://example.com/rules",
        CollectionMode.FULL_AUDIT,
        20,
        fetch_text,
        lambda _: ({}, {}),
    )

    assert requested == ["https://example.com/rules"]
    assert crawl.pages_succeeded == 1
    assert crawl.stop_reason == "single_page_completed"


# 動態入口必須維持獨立型態，靜態回應未命中時由語意驗證失敗關閉。
def test_dynamic_page_uses_single_page_contract() -> None:
    crawler = select_program_entry_crawler(ProgramSourceType.DYNAMIC_PAGE)
    crawl = crawler.fetch_pages(
        "https://example.com/application",
        CollectionMode.INCREMENTAL,
        20,
        lambda _: "<button>確定</button>",
        lambda _: ({}, {}),
    )

    assert crawl.completeness == "incremental"
    assert crawl.pages_succeeded == 1
