# -*- coding: utf-8 -*-

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EligibleLink:
    """LINE 顯示用的獎學金名稱、入口與申請狀態備註。"""

    title: str
    url: str
    status_note: str = ""


# 這些是使用者逐項確認要持續追蹤的方案。
# 申請期間與自動解析結果不應讓它們從每日 LINE 清單消失。
USER_CONFIRMED_ELIGIBLE_LINKS: tuple[EligibleLink, ...] = (
    EligibleLink(
        title="行天宮資優學生長期獎助學金",
        url="https://www.ht.org.tw/religion178.htm",
    ),
    EligibleLink(
        title="耀登炳南大專校院優秀人才獎學金",
        url="https://www.auden.com.tw/2026scholarship/",
    ),
    EligibleLink(
        title="新北市新莊區聯合優秀獎學金",
        url="https://xinzhuangawards.ntpc.gov.tw/",
        status_note="狀態：尚未開放（115年已截止，等待116年公告）",
    ),
    EligibleLink(
        title="王雲五先生自學獎學金",
        url="https://yunwu.org.tw/y/news/category/6",
    ),
    EligibleLink(
        title="資訊人社會關懷獎學金",
        url="https://itss.csroc.org.tw/about/",
    ),
)


def links_from_scholarships(items: Iterable[object]) -> tuple[EligibleLink, ...]:
    """從動態判定結果擷取硬性資格符合的名稱與正文連結。"""

    links: list[EligibleLink] = []
    for item in items:
        hard_status = str(getattr(item, "hard_eligibility_status", "") or "")
        status = hard_status or str(getattr(item, "eligibility_status", "") or "")
        if status != "eligible":
            continue
        title = str(getattr(item, "title", "") or "").strip()
        url = str(
            getattr(item, "detail_url", "")
            or getattr(item, "source_url", "")
            or ""
        ).strip()
        if title and url:
            links.append(EligibleLink(title=title, url=url))
    return tuple(links)


def merge_links(*groups: Iterable[EligibleLink]) -> tuple[EligibleLink, ...]:
    """依輸入順序合併並以網址去重。"""

    merged: list[EligibleLink] = []
    seen_urls: set[str] = set()
    for group in groups:
        for link in group:
            if not link.url or link.url in seen_urls:
                continue
            seen_urls.add(link.url)
            merged.append(link)
    return tuple(merged)


def build_line_message(
    links: Iterable[EligibleLink],
    *,
    checked_at: datetime,
    max_length: int,
    collected_count: int = 0,
) -> str:
    """建立固定每日 LINE 格式，顯示統計、名稱、連結與必要狀態。"""

    visible_links = tuple(links)
    lines = [
        "獎學金每日檢查完成",
        f"時間：{checked_at:%Y-%m-%d %H:%M}",
        f"本次蒐集公告：{collected_count}",
        f"本次符合並通知：{len(visible_links)}",
    ]
    if not visible_links:
        lines.extend(["", "目前沒有符合資格且仍可申請的獎學金。"])
        return "\n".join(lines)[:max_length]

    lines.append("")
    for index, link in enumerate(visible_links, start=1):
        block = [f"{index}. {link.title}", link.url]
        if link.status_note:
            block.append(link.status_note)
        candidate = "\n".join([*lines, *block])
        if len(candidate) > max_length:
            break
        lines.extend(block)
    return "\n".join(lines)
