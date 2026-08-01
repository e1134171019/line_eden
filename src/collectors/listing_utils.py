# -*- coding: utf-8 -*-

from datetime import date
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

_DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>1\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
)
_PAGE_COUNT_PATTERN = re.compile(r"共\s*(?P<count>\d+)\s*頁")
_PAGE_PATH_PATTERN = re.compile(r"/page/(?P<number>\d+)(?:/|$)")
_PAGE_SUFFIX_PATTERN = re.compile(r"/page/\d+$")
_DYNA_URL_PREFIX_PATTERN = re.compile(
    r"urlPrefix\s*:\s*['\"](?P<prefix>[^'\"]*PAGE[^'\"]*)['\"]"
)
_DYNA_TOTAL_PAGE_PATTERN = re.compile(r"totalPage\s*:\s*(?P<count>\d+)")
_DYNA_CURRENT_PAGE_PATTERN = re.compile(r"currentPage\s*:\s*(?P<number>\d+)")
_NEXT_LABELS = frozenset({"下一頁", "下頁", "next", ">", "»"})
_PAGE_QUERY_KEYS = frozenset({"page", "pageno", "page_no", "pageindex", "page_index"})


# 從文字抽取西元或民國日期並統一成 ISO 格式。
def extract_date(text: str) -> str:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        year = int(match.group("year"))
        if year < 1911:
            year += 1911
        try:
            return date(year, int(match.group("month")), int(match.group("day"))).isoformat()
        except ValueError:
            continue
    return ""


# 明確「共 N 頁」優先；否則只採同列表頁碼與可信 DYNA 設定。
def detect_total_pages(html: str, base_url: str = "") -> int:
    soup = BeautifulSoup(html, "html.parser")
    explicit = _explicit_page_count(soup)
    if explicit is not None:
        return explicit
    total_match = _DYNA_TOTAL_PAGE_PATTERN.search(html)
    if total_match is not None:
        return int(total_match.group("count"))
    numbers = [1]
    if base_url:
        numbers.extend(number for number, _ in numbered_page_urls(html, base_url))
    return max(numbers)


# 解析 DYNA CMS；依 currentPage 產生目前頁以外的所有分頁網址。
def dyna_page_urls(
    html: str,
    base_url: str,
    *,
    skip_page_one: bool = False,
) -> list[tuple[int, str]]:
    prefix_match = _DYNA_URL_PREFIX_PATTERN.search(html)
    total_match = _DYNA_TOTAL_PAGE_PATTERN.search(html)
    if prefix_match is None or total_match is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    explicit = _explicit_page_count(soup)
    total = explicit if explicit is not None else int(total_match.group("count"))
    current_match = _DYNA_CURRENT_PAGE_PATTERN.search(html)
    current = int(current_match.group("number")) if current_match else 1
    prefix = _prefer_base_https(
        base_url,
        urljoin(base_url, prefix_match.group("prefix")),
    )
    return [
        (page, prefix.replace("PAGE", str(page)))
        for page in range(1, total + 1)
        if page != current and not (skip_page_one and page == 1)
    ]


# 找出頁面中的數字分頁連結，依頁碼排序。
def numbered_page_urls(html: str, base_url: str) -> list[tuple[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[int, str] = {}
    for link in soup.find_all("a", href=True):
        number = _page_number(link)
        href = str(link.get("href", "")).strip()
        if number is None or not href or href.casefold().startswith("javascript:"):
            continue
        url = _prefer_base_https(base_url, urljoin(base_url, href))
        if _same_listing_host_and_path(base_url, url):
            result[number] = url
    return sorted(result.items())


# 找出同一列表的下一頁連結。
def next_page_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).split()).casefold()
        rel = _rel_values(link)
        if label not in _NEXT_LABELS and "next" not in rel:
            continue
        href = str(link.get("href", "")).strip()
        if not href or href.casefold().startswith("javascript:"):
            continue
        url = _prefer_base_https(base_url, urljoin(base_url, href))
        if _same_listing_host_and_path(base_url, url):
            return url
    return None


# HTTPS 入口頁不得因站內舊式絕對網址降級成 HTTP。
def _prefer_base_https(base_url: str, candidate_url: str) -> str:
    base = urlparse(base_url)
    candidate = urlparse(candidate_url)
    if (
        base.scheme.casefold() == "https"
        and candidate.scheme.casefold() == "http"
        and base.hostname == candidate.hostname
    ):
        return candidate._replace(scheme="https").geturl()
    return candidate_url


# 正規化 BeautifulSoup 的 rel 屬性。
def _rel_values(link: Tag) -> set[str]:
    value = link.get("rel")
    if value is None:
        return set()
    if isinstance(value, str):
        return {part.casefold() for part in value.split()}
    return {str(part).casefold() for part in value}


# 只把 /page/N 或明確 page query 的數字連結視為頁碼。
def _page_number(link: Tag) -> int | None:
    href = str(link.get("href", ""))
    parsed = urlparse(href)
    path_match = _PAGE_PATH_PATTERN.search(parsed.path)
    if path_match:
        return int(path_match.group("number"))
    label = " ".join(link.get_text(" ", strip=True).split())
    if not label.isdigit() or not _has_page_query(parsed.query):
        return None
    return int(label)


# 判斷 query string 是否包含明確分頁參數。
def _has_page_query(query: str) -> bool:
    keys = {key.casefold() for key in parse_qs(query, keep_blank_values=True)}
    return bool(keys & _PAGE_QUERY_KEYS)


# 取得頁面正文中明確宣告的總頁數。
def _explicit_page_count(soup: BeautifulSoup) -> int | None:
    match = _PAGE_COUNT_PATTERN.search(soup.get_text(" ", strip=True))
    return int(match.group("count")) if match else None


# 限制翻頁不得離開同一主機與同一列表路徑族群。
def _same_listing_host_and_path(base_url: str, candidate_url: str) -> bool:
    base = urlparse(base_url)
    candidate = urlparse(candidate_url)
    if candidate.hostname != base.hostname:
        return False
    base_path = base.path.rstrip("/")
    candidate_path = candidate.path.rstrip("/")
    if candidate_path == base_path:
        return True
    return _listing_root(base_path) == _listing_root(candidate_path)


# 移除 /page/N 後比較同一分頁列表根路徑。
def _listing_root(path: str) -> str:
    return _PAGE_SUFFIX_PATTERN.sub("", path)
