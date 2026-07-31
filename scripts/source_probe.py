# -*- coding: utf-8 -*-

import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from config import (
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    LHU_SCHOLARSHIP_URL,
    SOURCE_MAX_PAGES,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.http_client import SafeHttpClient
from src.collectors.moe_overseas_collector import (
    OVERSEAS_CHILD_SOURCES,
    MoeOverseasCollector,
)

_PAGE_LABELS = {"1", "2", "3", "4", "5", ">", ">>", "»", "下一頁", "下頁"}
_ROC_DATE = re.compile(r"1\d{2}[./-]\d{1,2}[./-]\d{1,2}")


def main() -> None:
    """輸出不含個資的分頁 HTML 屬性與留學子站逐項診斷。"""
    with SafeHttpClient(HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT) as client:
        _probe_lhu(client)
        _probe_overseas(client)


# 輸出龍華頁碼元素、父層與控制分頁的 JavaScript。
def _probe_lhu(client: SafeHttpClient) -> None:
    print("\nLHU 分頁候選：")
    html = client.get_text(LHU_SCHOLARSHIP_URL)
    soup = BeautifulSoup(html, "html.parser")
    first_page_link: Tag | None = None
    for link in soup.find_all("a"):
        label = " ".join(link.get_text(" ", strip=True).split())
        if label not in _PAGE_LABELS and "頁" not in label:
            continue
        attributes = {
            key: value
            for key, value in link.attrs.items()
            if key
            in {"href", "onclick", "data-page", "data-index", "rel", "class"}
        }
        print(f"- label={label!r} attrs={attributes!r}")
        if label == "1" and "_cgptlist_gopage" in link.get("class", []):
            first_page_link = link
    if first_page_link is not None:
        parent = first_page_link.parent
        grandparent = parent.parent if isinstance(parent, Tag) else None
        container = grandparent if isinstance(grandparent, Tag) else parent
        print(f"LHU 分頁父層 HTML：{str(container)[:4000]}")
    for script in soup.find_all("script"):
        text = script.get_text("\n", strip=True)
        if "cgptlist" in text.casefold() or "gopage" in text.casefold():
            print(f"LHU 分頁 JavaScript：{text[:8000]}")


# 輸出四個留學子站結果；零解析時顯示日期節點周邊結構。
def _probe_overseas(client: SafeHttpClient) -> None:
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
        if not records:
            _probe_zero_record_page(client, child.list_url)


# 顯示零解析頁面的標題、公告連結與民國日期最近父層。
def _probe_zero_record_page(client: SafeHttpClient, url: str) -> None:
    html = client.get_text(url)
    soup = BeautifulSoup(html, "html.parser")
    headings = [
        " ".join(tag.get_text(" ", strip=True).split())
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    ]
    print(f"  headings={headings[:30]!r}")
    for link in soup.find_all("a", href=True):
        text = " ".join(link.get_text(" ", strip=True).split())
        if "公費留學" in text or "留學考試" in text:
            parent = link.parent
            ancestor = parent.parent if isinstance(parent, Tag) and isinstance(parent.parent, Tag) else parent
            print(
                f"  announcement-link text={text!r} href={link.get('href')!r} "
                f"html={str(ancestor)[:5000]}"
            )
    printed: set[str] = set()
    for text_node in soup.find_all(string=lambda value: value and _ROC_DATE.search(value)):
        parent = text_node.parent
        if not isinstance(parent, Tag):
            continue
        ancestor: Tag = parent
        for _ in range(3):
            if isinstance(ancestor.parent, Tag):
                ancestor = ancestor.parent
        snippet = str(ancestor)[:6000]
        if snippet in printed:
            continue
        printed.add(snippet)
        print(f"  roc-date-html={snippet}")


if __name__ == "__main__":
    main()
