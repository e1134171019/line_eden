# -*- coding: utf-8 -*-

from urllib.parse import urlparse

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
LHU_CONTENT_SELECTORS = (".mpgdetail", ".module-detail", ".mcont")
REMOVE_SELECTORS = (
    "script, style, noscript, header, nav, footer, aside, form, "
    ".header, .footer, .navbar, .menu, .sidebar, .breadcrumb, "
    ".banner, .slider, .carousel, .bx-wrapper, .swiper, .owl-carousel, .module-banner"
)
MIN_CONTENT_LENGTH = 20


# 從公告 HTML 中擷取主內容文字，排除導覽、橫幅與頁尾雜訊。
def extract_announcement_text(
    html: str,
    title: str = "",
    source_url: str = "",
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _remove_boilerplate(soup)
    root = select_announcement_root(soup, title, source_url)
    text = _normalized_text(root)
    if len(text) < MIN_CONTENT_LENGTH:
        raise ValueError("無法可靠定位公告正文")
    return text


# 依網站結構與標題位置選擇最接近公告正文的容器。
def select_announcement_root(
    soup: BeautifulSoup,
    title: str,
    source_url: str,
) -> Tag | None:
    site_root = _select_site_root(soup, title, source_url)
    if site_root is not None:
        return site_root
    title_root = _select_title_root(soup, title)
    if title_root is not None:
        return title_root
    candidates = [node for selector in CONTENT_SELECTORS for node in soup.select(selector)]
    if not candidates:
        candidates = soup.select("section, div")
    return max(_unique_tags(candidates), key=_content_score, default=None)


# 龍華子網站優先使用其固定公告明細容器，避免選到整頁祖先節點。
def _select_site_root(
    soup: BeautifulSoup,
    title: str,
    source_url: str,
) -> Tag | None:
    host = (urlparse(source_url).hostname or "").lower()
    if not host.endswith("lhu.edu.tw"):
        return None
    candidates = [node for selector in LHU_CONTENT_SELECTORS for node in soup.select(selector)]
    return _smallest_reliable_candidate(candidates, title)


# 從標題向上尋找最小且足以包含正文的容器。
def _select_title_root(soup: BeautifulSoup, title: str) -> Tag | None:
    candidates = _title_ancestors(soup, title)
    return _smallest_reliable_candidate(candidates, title)


# 選擇包含標題且文字量足夠的最小容器，降低共用橫幅污染。
def _smallest_reliable_candidate(nodes: list[Tag], title: str) -> Tag | None:
    normalized_title = " ".join(title.split())
    reliable = [node for node in _unique_tags(nodes) if len(_normalized_text(node)) >= MIN_CONTENT_LENGTH]
    titled = [node for node in reliable if normalized_title and normalized_title in _normalized_text(node)]
    candidates = titled or reliable
    return min(candidates, key=lambda node: len(_normalized_text(node)), default=None)


# 移除不屬於公告正文的常見節點。
def _remove_boilerplate(soup: BeautifulSoup) -> None:
    for node in soup.select(REMOVE_SELECTORS):
        node.decompose()


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
    penalty = 1000 if any(word in class_text.lower() for word in ("footer", "menu", "nav")) else 0
    return text_length - link_length * 3 - penalty


# 將節點文字壓縮為單一空白格式。
def _normalized_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())
