# -*- coding: utf-8 -*-

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.extractors.announcement_content_extractor import select_announcement_root

SUPPORTED_SUFFIXES = (".pdf", ".docx")
DOCUMENT_LABELS = ("附件", "附檔", "下載", "辦法", "簡章", "資格", "評選", "推薦書")
HIGH_VALUE_LABELS = ("辦法", "資格", "簡章", "評選", "規定", "要點", "申請須知")
LOW_VALUE_LABELS = ("申請表", "推薦書", "同意書", "切結書")


@dataclass(frozen=True)
class AttachmentLinkInventory:
    """公告附件總數與依價值排序後的選取網址。"""

    selected_urls: tuple[str, ...]
    discovered_count: int


# 從公告正文區塊擷取可解析的 PDF 與 DOCX 附件網址。
def extract_attachment_links(
    html: str,
    base_url: str,
    title: str,
    max_count: int,
) -> list[str]:
    inventory = extract_attachment_inventory(html, base_url, title, max_count)
    return list(inventory.selected_urls)


# 建立附件總數與安全上限內的選取清單。
def extract_attachment_inventory(
    html: str,
    base_url: str,
    title: str,
    max_count: int,
) -> AttachmentLinkInventory:
    soup = BeautifulSoup(html, "html.parser")
    root = select_announcement_root(soup, title, base_url)
    candidates = _collect_links(root, base_url)
    ranked = sorted(candidates, key=lambda item: item[0], reverse=True)
    selected = tuple(url for _, url in ranked[:max_count])
    return AttachmentLinkInventory(selected, len(ranked))


# 收集附件連結並依內容價值建立排序分數。
def _collect_links(root: Tag | None, base_url: str) -> list[tuple[int, str]]:
    if root is None:
        return []
    seen: set[str] = set()
    records: list[tuple[int, str]] = []
    for link in root.select("a[href]"):
        url = urljoin(base_url, link.get("href", "").strip())
        label = " ".join(link.get_text(" ", strip=True).split())
        if url not in seen and _is_supported_document(url, label):
            seen.add(url)
            records.append((_attachment_score(url, label), url))
    return records


# 判斷網址或連結文字是否代表可解析文件。
def _is_supported_document(url: str, label: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith(SUPPORTED_SUFFIXES):
        return True
    normalized_label = label.lower()
    has_suffix = normalized_label.endswith(SUPPORTED_SUFFIXES)
    return has_suffix and any(marker in label for marker in DOCUMENT_LABELS)


# 優先處理辦法、資格與簡章，降低只下載空白表單的機率。
def _attachment_score(url: str, label: str) -> int:
    score = 10 if urlparse(url).path.lower().endswith(".pdf") else 5
    score += sum(20 for marker in HIGH_VALUE_LABELS if marker in label)
    score -= sum(10 for marker in LOW_VALUE_LABELS if marker in label)
    return score
