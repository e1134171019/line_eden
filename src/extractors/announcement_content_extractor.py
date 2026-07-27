# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup, Tag

CONTENT_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    ".mpgdetail",
    ".mcont",
    ".module-detail",
    ".article-content",
    ".news-content",
    ".content-body",
)
REMOVE_SELECTORS = (
    "script, style, noscript, header, nav, footer, aside, form, "
    ".header, .footer, .navbar, .menu, .sidebar, .breadcrumb"
)
MIN_CONTENT_LENGTH = 20


# 從公告 HTML 中擷取主內容文字，排除導覽與頁尾雜訊。
def extract_announcement_text(html: str, title: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    _remove_boilerplate(soup)
    candidates = _collect_candidates(soup, title)
    root = max(candidates, key=_content_score, default=None)
    text = _normalized_text(root)
    if len(text) < MIN_CONTENT_LENGTH:
        raise ValueError("無法可靠定位公告正文")
    return text


# 移除不屬於公告正文的常見節點。
def _remove_boilerplate(soup: BeautifulSoup) -> None:
    for node in soup.select(REMOVE_SELECTORS):
        node.decompose()


# 收集已知內容容器與標題附近的候選節點。
def _collect_candidates(soup: BeautifulSoup, title: str) -> list[Tag]:
    candidates = [node for selector in CONTENT_SELECTORS for node in soup.select(selector)]
    candidates.extend(_title_ancestors(soup, title))
    if not candidates:
        candidates.extend(soup.select("section, div"))
    return _unique_tags(candidates)


# 從公告標題文字向上尋找可能的正文容器。
def _title_ancestors(soup: BeautifulSoup, title: str) -> list[Tag]:
    normalized_title = " ".join(title.split())
    if not normalized_title:
        return []
    nodes = soup.find_all(string=lambda value: value and normalized_title in " ".join(value.split()))
    return [ancestor for node in nodes for ancestor in _walk_ancestors(node.parent)]


# 向上收集有限層級的主要容器。
def _walk_ancestors(node: Tag | None) -> list[Tag]:
    ancestors: list[Tag] = []
    current = node
    for _ in range(5):
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


# 以正文長度與連結密度評估候選容器品質。
def _content_score(node: Tag) -> int:
    text_length = len(_normalized_text(node))
    link_length = sum(len(_normalized_text(link)) for link in node.select("a"))
    class_text = " ".join(node.get("class", []))
    penalty = 1000 if any(word in class_text.lower() for word in ("footer", "menu", "nav")) else 0
    return text_length - link_length * 3 - penalty


# 將節點文字壓縮為單一空白格式。
def _normalized_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())
