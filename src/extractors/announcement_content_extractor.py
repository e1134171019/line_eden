# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup, Tag

from src.models.detail_extraction import (
    AnnouncementContentExtraction,
    DetailExtractionPolicy,
    ExtractionMode,
    policy_for_url,
)


# 從公告 HTML 中擷取主內容文字，保留政策與實際 selector 診斷。
def extract_announcement_content(
    html: str,
    title: str = "",
    source_url: str = "",
    policy: DetailExtractionPolicy | None = None,
) -> AnnouncementContentExtraction:
    effective = policy or policy_for_url(source_url)
    soup = BeautifulSoup(html, "html.parser")
    _remove_boilerplate(soup, effective)
    selected, selector, fallback = _select_with_policy(soup, title, effective)
    text = _normalized_text(selected)
    if len(text) < effective.min_content_length:
        raise ValueError("無法可靠定位公告正文")
    return AnnouncementContentExtraction(
        text=text,
        policy_name=effective.name,
        policy_version=effective.version,
        policy_hash=effective.config_hash(),
        selected_selector=selector,
        heuristic_fallback=fallback,
    )


# 保留既有只取文字的介面。
def extract_announcement_text(
    html: str,
    title: str = "",
    source_url: str = "",
) -> str:
    return extract_announcement_content(html, title, source_url).text


# 保留附件發現使用的公告 root 介面，與正文政策共用同一選取邏輯。
def select_announcement_root(
    soup: BeautifulSoup,
    title: str = "",
    source_url: str = "",
) -> Tag | None:
    effective = policy_for_url(source_url)
    selected, _, _ = _select_with_policy(soup, title, effective)
    return selected


# 依政策 selectors、標題祖先與通用 heuristic 順序選取正文。
def _select_with_policy(
    soup: BeautifulSoup,
    title: str,
    policy: DetailExtractionPolicy,
) -> tuple[Tag | None, str, bool]:
    for selector in policy.include_selectors:
        candidates = [node for node in soup.select(selector) if isinstance(node, Tag)]
        selected = _smallest_reliable_candidate(candidates, title, policy.min_content_length)
        if selected is not None:
            return selected, selector, False

    if policy.mode == ExtractionMode.STRICT_SELECTORS:
        raise ValueError(f"找不到 strict 正文 selector：{policy.name}")

    title_root = _select_title_root(soup, title, policy.min_content_length)
    if title_root is not None:
        return title_root, "title-ancestor", True

    if policy.mode == ExtractionMode.PREFER_SELECTORS or policy.mode == ExtractionMode.AUTO:
        candidates = soup.select("article, main, [role='main'], section, div")
        return max(_unique_tags(candidates), key=_content_score, default=None), "heuristic", True
    return None, "none", True


# 從標題向上尋找最小且足以包含正文的容器。
def _select_title_root(
    soup: BeautifulSoup,
    title: str,
    minimum_length: int,
) -> Tag | None:
    candidates = _title_ancestors(soup, title)
    return _smallest_reliable_candidate(candidates, title, minimum_length)


# 選擇包含標題且文字量足夠的最小容器。
def _smallest_reliable_candidate(
    nodes: list[Tag],
    title: str,
    minimum_length: int,
) -> Tag | None:
    normalized_title = " ".join(title.split())
    reliable = [
        node
        for node in _unique_tags(nodes)
        if len(_normalized_text(node)) >= minimum_length
    ]
    titled = [
        node
        for node in reliable
        if normalized_title and normalized_title in _normalized_text(node)
    ]
    candidates = titled or reliable
    return min(candidates, key=lambda node: len(_normalized_text(node)), default=None)


# 依政策移除不屬於公告正文的節點。
def _remove_boilerplate(soup: BeautifulSoup, policy: DetailExtractionPolicy) -> None:
    for selector in policy.subtractive_selectors:
        for node in soup.select(selector):
            node.decompose()


# 從公告標題文字向上尋找可能的正文容器。
def _title_ancestors(soup: BeautifulSoup, title: str) -> list[Tag]:
    normalized_title = " ".join(title.split())
    if not normalized_title:
        return []
    nodes = soup.find_all(
        string=lambda value: value and normalized_title in " ".join(value.split())
    )
    return [ancestor for node in nodes for ancestor in _walk_ancestors(node.parent)]


# 向上收集有限層級的主要容器。
def _walk_ancestors(node: Tag | None) -> list[Tag]:
    ancestors: list[Tag] = []
    current = node
    for _ in range(6):
        if current is None:
            break
        if current.name in {"article", "main", "section", "div"}:
            ancestors.append(current)
        current = current.parent if isinstance(current.parent, Tag) else None
    return ancestors


# 移除重複候選節點並保留原順序。
def _unique_tags(nodes: list[Tag]) -> list[Tag]:
    seen: set[int] = set()
    unique: list[Tag] = []
    for node in nodes:
        identity = id(node)
        if identity not in seen:
            seen.add(identity)
            unique.append(node)
    return unique


# 以正文長度與連結密度評估通用候選容器品質。
def _content_score(node: Tag) -> int:
    text_length = len(_normalized_text(node))
    link_length = sum(len(_normalized_text(link)) for link in node.select("a"))
    class_text = " ".join(node.get("class", []))
    penalty = 1000 if any(
        word in class_text.lower() for word in ("footer", "menu", "nav")
    ) else 0
    return text_length - link_length * 3 - penalty


# 將節點文字壓縮為單一空白格式。
def _normalized_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())
