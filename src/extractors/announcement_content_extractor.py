# -*- coding: utf-8 -*-

from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from config import (
    DEFAULT_DETAIL_EXTRACTION_POLICY,
    DETAIL_EXTRACTION_POLICY_RULES,
)
from src.models.detail_extraction import (
    DetailExtractionPolicy,
    ExtractedAnnouncementContent,
    ExtractionMode,
    build_extraction_policy_hash,
    resolve_detail_extraction_policy,
)


@dataclass(frozen=True)
class _RootSelection:
    root: Tag | None
    selector_used: str
    used_fallback: bool


# 從公告 HTML 中擷取正文與 effective policy metadata。
def extract_announcement_content(
    html: str,
    title: str = "",
    source_url: str = "",
    policy: DetailExtractionPolicy | None = None,
) -> ExtractedAnnouncementContent:
    effective_policy = policy or resolve_detail_extraction_policy(
        source_url,
        DETAIL_EXTRACTION_POLICY_RULES,
        DEFAULT_DETAIL_EXTRACTION_POLICY,
    )
    soup = BeautifulSoup(html, "html.parser")
    _remove_boilerplate(soup, effective_policy.subtractive_selectors)
    selection = _select_announcement_root(soup, title, effective_policy)
    text = _normalized_text(selection.root)
    if len(text) < effective_policy.min_content_length:
        raise ValueError("無法可靠定位公告正文")
    return ExtractedAnnouncementContent(
        text=text,
        selector_used=selection.selector_used,
        used_fallback=selection.used_fallback,
        policy_name=effective_policy.name,
        policy_hash=build_extraction_policy_hash(effective_policy),
    )


# 相容既有呼叫端，只回傳公告正文文字。
def extract_announcement_text(
    html: str,
    title: str = "",
    source_url: str = "",
) -> str:
    return extract_announcement_content(html, title, source_url).text


# 相容附件連結擷取器，回傳本次 policy 選出的根節點。
def select_announcement_root(
    soup: BeautifulSoup,
    title: str,
    source_url: str,
) -> Tag | None:
    policy = resolve_detail_extraction_policy(
        source_url,
        DETAIL_EXTRACTION_POLICY_RULES,
        DEFAULT_DETAIL_EXTRACTION_POLICY,
    )
    _remove_boilerplate(soup, policy.subtractive_selectors)
    return _select_announcement_root(soup, title, policy).root


# 根據 policy mode 決定 selector 與 heuristic 的優先順序。
def _select_announcement_root(
    soup: BeautifulSoup,
    title: str,
    policy: DetailExtractionPolicy,
) -> _RootSelection:
    selector_selection = _select_policy_root(soup, title, policy)
    if policy.mode is ExtractionMode.STRICT_SELECTORS:
        if selector_selection.root is None:
            raise ValueError(f"來源 {policy.name} 的正文 selector 未匹配")
        return selector_selection
    if policy.mode is ExtractionMode.PREFER_SELECTORS and selector_selection.root:
        return selector_selection

    title_root = _select_title_root(soup, title, policy.min_content_length)
    if title_root is not None:
        return _RootSelection(title_root, "title-ancestor", True)
    if selector_selection.root is not None:
        return selector_selection
    candidates = soup.select("section, div")
    root = max(_unique_tags(candidates), key=_content_score, default=None)
    return _RootSelection(root, "heuristic:section,div", True)


# 從設定的 selectors 中選擇最小且可靠的正文容器。
def _select_policy_root(
    soup: BeautifulSoup,
    title: str,
    policy: DetailExtractionPolicy,
) -> _RootSelection:
    candidates = [
        (selector, node)
        for selector in policy.include_selectors
        for node in soup.select(selector)
    ]
    nodes = [node for _, node in candidates]
    selected = _smallest_reliable_candidate(nodes, title, policy.min_content_length)
    if selected is None:
        return _RootSelection(None, "", False)
    selector = next(
        candidate_selector
        for candidate_selector, node in candidates
        if node is selected
    )
    return _RootSelection(selected, selector, False)


# 從標題向上尋找最小且足以包含正文的容器。
def _select_title_root(
    soup: BeautifulSoup,
    title: str,
    min_content_length: int,
) -> Tag | None:
    candidates = _title_ancestors(soup, title)
    return _smallest_reliable_candidate(candidates, title, min_content_length)


# 選擇包含標題且文字量足夠的最小容器，降低共用橫幅污染。
def _smallest_reliable_candidate(
    nodes: list[Tag],
    title: str,
    min_content_length: int,
) -> Tag | None:
    normalized_title = " ".join(title.split())
    reliable = [
        node
        for node in _unique_tags(nodes)
        if len(_normalized_text(node)) >= min_content_length
    ]
    titled = [
        node
        for node in reliable
        if normalized_title and normalized_title in _normalized_text(node)
    ]
    candidates = titled or reliable
    return min(candidates, key=lambda node: len(_normalized_text(node)), default=None)


# 移除不屬於公告正文的來源設定節點。
def _remove_boilerplate(
    soup: BeautifulSoup,
    subtractive_selectors: tuple[str, ...],
) -> None:
    for selector in subtractive_selectors:
        for node in soup.select(selector):
            node.decompose()


# 從公告標題文字向上尋找可能的正文容器。
def _title_ancestors(soup: BeautifulSoup, title: str) -> list[Tag]:
    normalized_title = " ".join(title.split())
    if not normalized_title:
        return []
    nodes = soup.find_all(
        string=lambda value: value
        and normalized_title in " ".join(value.split())
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
    noisy_words = ("footer", "menu", "nav")
    penalty = 1000 if any(word in class_text.lower() for word in noisy_words) else 0
    return text_length - link_length * 3 - penalty


# 將節點文字壓縮為單一空白格式。
def _normalized_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())
