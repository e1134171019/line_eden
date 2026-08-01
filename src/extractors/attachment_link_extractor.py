# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from config import ATTACHMENT_SCOPE_MAX_DEPTH
from src.extractors.announcement_content_extractor import select_announcement_root

SUPPORTED_SUFFIXES = (".pdf", ".doc", ".docx", ".odt")
DOCUMENT_LABELS = (
    "附件",
    "附檔",
    "下載",
    "辦法",
    "簡章",
    "資格",
    "評選",
    "推薦書",
    "申請須知",
)
HIGH_VALUE_LABELS = ("辦法", "資格", "簡章", "評選", "規定", "要點", "申請須知")
FORM_LABELS = ("申請表", "推薦書", "報名表")
SUPPORTING_LABELS = ("證明書", "同意書", "切結書", "聲明書", "名冊")
GENERIC_LABELS = ("附件", "附檔", "檔案", "文件下載", "下載文件")
RULES = "rules"
GENERIC_ATTACHMENT = "generic_attachment"
APPLICATION_FORM = "application_form"
SUPPORTING_DOCUMENT = "supporting_document"
UNRELATED = "unrelated"
_SCRIPT_URL = re.compile(
    r"(?:window\.open|location(?:\.href)?)\s*\(?\s*['\"]([^'\"]+)['\"]"
)
_DRIVE_FILE_ID = re.compile(r"/(?:file|document)/d/([^/]+)")


@dataclass(frozen=True)
class AttachmentLinkInventory:
    """公告附件總數、角色與依價值排序後的選取網址。"""

    selected_urls: tuple[str, ...]
    discovered_count: int
    selected_roles: tuple[str, ...] = tuple()
    discovered_rules_count: int = 0
    selected_labels: tuple[str, ...] = tuple()
    discovered_generic_count: int = 0

    def role_at(self, index: int) -> str:
        if index < len(self.selected_roles):
            return self.selected_roles[index]
        return "unknown"

    def label_at(self, index: int) -> str:
        if index < len(self.selected_labels):
            return self.selected_labels[index]
        return ""


def extract_attachment_links(
    html: str,
    base_url: str,
    title: str,
    max_count: int,
) -> list[str]:
    inventory = extract_attachment_inventory(html, base_url, title, max_count)
    return list(inventory.selected_urls)


def extract_attachment_inventory(
    html: str,
    base_url: str,
    title: str,
    max_count: int,
) -> AttachmentLinkInventory:
    soup = BeautifulSoup(html, "html.parser")
    root = select_announcement_root(soup, title, base_url)
    scope = _select_attachment_scope(root, base_url)
    candidates = _collect_links(scope, base_url)
    ranked = sorted(candidates, key=lambda item: item[0], reverse=True)
    selected = ranked[:max_count]
    selected_urls = tuple(url for _, url, _, _ in selected)
    selected_labels = tuple(label for _, _, label, _ in selected)
    selected_roles = tuple(role for _, _, _, role in selected)
    rules_count = sum(role == RULES for _, _, _, role in ranked)
    generic_count = sum(role == GENERIC_ATTACHMENT for _, _, _, role in ranked)
    return AttachmentLinkInventory(
        selected_urls=selected_urls,
        discovered_count=len(ranked),
        selected_roles=selected_roles,
        discovered_rules_count=rules_count,
        selected_labels=selected_labels,
        discovered_generic_count=generic_count,
    )


def _select_attachment_scope(root: Tag | None, base_url: str) -> Tag | None:
    current = root
    for _ in range(ATTACHMENT_SCOPE_MAX_DEPTH):
        if current is None:
            break
        if _collect_links(current, base_url):
            return current
        current = _safe_parent(current)
    return root


def _safe_parent(node: Tag) -> Tag | None:
    parent = node.parent
    if not isinstance(parent, Tag) or parent.name in {"body", "html"}:
        return None
    return parent


def _collect_links(root: Tag | None, base_url: str) -> list[tuple[int, str, str, str]]:
    if root is None:
        return []
    seen: set[str] = set()
    records: list[tuple[int, str, str, str]] = []
    selectors = "a[href], a[data-url], a[data-href], button[data-url], button[onclick]"
    for link in root.select(selectors):
        target = _link_target(link)
        url = _normalize_download_url(urljoin(base_url, target))
        label = " ".join(link.get_text(" ", strip=True).split())
        if not target or url in seen or not _is_supported_document(url, label):
            continue
        seen.add(url)
        role = classify_attachment_role(label)
        records.append((_attachment_score(url, label, role), url, label, role))
    return records


def classify_attachment_role(label: str) -> str:
    if any(marker in label for marker in HIGH_VALUE_LABELS):
        return RULES
    if any(marker in label for marker in FORM_LABELS):
        return APPLICATION_FORM
    if any(marker in label for marker in SUPPORTING_LABELS):
        return SUPPORTING_DOCUMENT
    if any(marker in label for marker in GENERIC_LABELS):
        return GENERIC_ATTACHMENT
    return UNRELATED


def _is_supported_document(url: str, label: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.lower()
    if path.endswith(SUPPORTED_SUFFIXES):
        return True
    normalized_label = label.lower().rstrip("。．. ")
    has_suffix = normalized_label.endswith(SUPPORTED_SUFFIXES)
    has_document_label = any(marker in label for marker in DOCUMENT_LABELS)
    return has_document_label and (has_suffix or bool(parsed.path or parsed.query))


def _link_target(link: Tag) -> str:
    """純函式：取得一般連結、資料屬性或簡單 JavaScript 下載網址。"""

    for attribute in ("href", "data-url", "data-href", "data-download-url"):
        value = str(link.get(attribute, "")).strip()
        if value and not value.casefold().startswith("javascript:"):
            return value
    script = str(link.get("onclick", ""))
    match = _SCRIPT_URL.search(script)
    return match.group(1).strip() if match else ""


def _normalize_download_url(url: str) -> str:
    """純函式：將公開 Google Drive／Docs 檢視頁轉成可下載資源。"""

    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    file_match = _DRIVE_FILE_ID.search(parsed.path)
    if host == "drive.google.com" and file_match:
        query = urlencode({"export": "download", "id": file_match.group(1)})
        return urlunparse(("https", "drive.google.com", "/uc", "", query, ""))
    if host == "docs.google.com" and file_match:
        path = f"/document/d/{file_match.group(1)}/export"
        return urlunparse(("https", host, path, "", "format=pdf", ""))
    if host == "drive.google.com" and parsed.path == "/open":
        file_ids = parse_qs(parsed.query).get("id", [])
        if file_ids:
            query = urlencode({"export": "download", "id": file_ids[0]})
            return urlunparse(("https", host, "/uc", "", query, ""))
    return url


def _attachment_score(url: str, label: str, role: str) -> int:
    score = 10 if urlparse(url).path.lower().endswith(".pdf") else 5
    role_bonus = {
        RULES: 80,
        GENERIC_ATTACHMENT: 50,
        APPLICATION_FORM: 30,
        SUPPORTING_DOCUMENT: 10,
        UNRELATED: 0,
    }
    score += role_bonus[role]
    score += sum(20 for marker in HIGH_VALUE_LABELS if marker in label)
    return score
