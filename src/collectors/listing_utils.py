# -*- coding: utf-8 -*-

from datetime import date
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

_DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>1\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
)
_PAGE_COUNT_PATTERN = re.compile(r"共\s*(?P<count>\d+)\s*頁")
_PAGE_PATH_PATTERN = re.compile(r"/page/(?P<number>\d+)(?:/|$)")
_NEXT_LABELS = frozenset({"下一頁", "下頁", "next", ">", "»"})


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


# 從頁面文字與數字頁碼連結推導總頁數。
def detect_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    text_match = _PAGE_COUNT_PATTERN.search(soup.get_text(" ", strip=True))
    numbers = [1]
    for link in soup.find_all("a", href=True):
        number = _page_number(link)
        if number is not None:
            numbers.append(number)
    if text_match:
        numbers.append(int(text_match.group("count")))
    return max(numbers)


# 找出頁面中的數字分頁連結，依頁碼排序。
def numbered_page_urls(html: str, base_url: str) -> list[tuple[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[int, str] = {}
    for link in soup.find_all("a", href=True):
        number = _page_number(link)
        href = str(link.get("href", "")).strip()
        if number is None or not href:
            continue
        url = urljoin(base_url, href)
        if _same_listing_host_and_path(base_url, url):
            result[number] = url
    return sorted(result.items())


# 找出同一列表的下一頁連結。
def next_page_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).split()).casefold()
        rel = {str(value).casefold() for value in link.get("rel", [])}
        if label not in _NEXT_LABELS and "next" not in rel:
            continue
        href = str(link.get("href", "")).strip()
        if not href:
            continue
        url = urljoin(base_url, href)
        if _same_listing_host_and_path(base_url, url):
            return url
    return None


# 從連結文字或 /page/N 路徑取得頁碼。
def _page_number(link: Tag) -> int | None:
    label = " ".join(link.get_text(" ", strip=True).split())
    if label.isdigit():
        return int(label)
    href = str(link.get("href", ""))
    match = _PAGE_PATH_PATTERN.search(urlparse(href).path)
    return int(match.group("number")) if match else None


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
    return candidate_path.startswith(f"{base_path}/page/")
