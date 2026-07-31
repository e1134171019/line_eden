# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT, LHU_SCHOLARSHIP_URL, SOURCE_MAX_PAGES
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.http_client import SafeHttpClient
from src.collectors.moe_overseas_collector import (
    OVERSEAS_CHILD_SOURCES,
    MoeOverseasCollector,
)

_PAGE_LABELS = {"1", "2", "3", "4", "5", ">", ">>", "»", "下一頁", "下頁"}


def main() -> None:
    """輸出不含個資的分頁 HTML 屬性與留學子站逐項診斷。"""
    print("\nLHU 分頁候選：")
    with SafeHttpClient(HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT) as client:
        html = client.get_text(LHU_SCHOLARSHIP_URL)
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a"):
            label = " ".join(link.get_text(" ", strip=True).split())
            if label not in _PAGE_LABELS and "頁" not in label:
                continue
            attributes = {
                key: value
                for key, value in link.attrs.items()
                if key in {"href", "onclick", "data-page", "data-index", "rel", "class"}
            }
            print(f"- label={label!r} attrs={attributes!r}")

        print("\n教育部留學子站診斷：")
        collector = MoeOverseasCollector(
            HTTP_TIMEOUT_SECONDS,
            HTTP_USER_AGENT,
            CollectionMode.FULL_AUDIT,
            SOURCE_MAX_PAGES,
        )
        for child in OVERSEAS_CHILD_SOURCES:
            try:
                records, diagnostic = collector._collect_child(client, child)
            except Exception as error:
                print(f"- {child.display_name}: exception={error}")
                continue
            print(
                f"- {child.display_name}: records={len(records)}, "
                f"completeness={diagnostic.completeness}, "
                f"pages={diagnostic.pages_succeeded}/{diagnostic.pages_detected}, "
                f"raw={diagnostic.raw_rows}, stop={diagnostic.stop_reason}, "
                f"error={diagnostic.error!r}"
            )


if __name__ == "__main__":
    main()
