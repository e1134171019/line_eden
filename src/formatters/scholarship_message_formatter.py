# -*- coding: utf-8 -*-

from src.models.scholarship import Scholarship


# 將待通知公告依每則訊息上限切成多批。
def split_scholarships(
    items: list[Scholarship],
    batch_size: int,
) -> list[list[Scholarship]]:
    if batch_size <= 0:
        raise ValueError("batch_size 必須大於 0")
    return [items[index:index + batch_size] for index in range(0, len(items), batch_size)]


# 建立每筆公告都包含獨立網址的 LINE 摘要。
def build_summary_message(
    items: list[Scholarship],
    batch_index: int,
    batch_count: int,
) -> str:
    lines = [f"【獎學金新公告｜第 {batch_index}/{batch_count} 則】"]
    for index, item in enumerate(items, start=1):
        lines.extend(_build_item_lines(index, item))
    return "\n".join(lines)


# 建立單筆公告在摘要中的日期、標題與連結。
def _build_item_lines(index: int, item: Scholarship) -> list[str]:
    return [
        f"{index}. {item.published_date}",
        item.title,
        item.source_url,
    ]
