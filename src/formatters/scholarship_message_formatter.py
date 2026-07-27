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


# 建立每筆公告都包含獨立網址與符合原因的 LINE 摘要。
def build_summary_message(
    items: list[Scholarship],
    batch_index: int,
    batch_count: int,
) -> str:
    lines = [f"【適合你的獎學金｜第 {batch_index}/{batch_count} 則】"]
    for index, item in enumerate(items, start=1):
        lines.extend(_build_item_lines(index, item))
    return "\n".join(lines)


# 建立單筆公告的日期、標題、符合原因與連結。
def _build_item_lines(index: int, item: Scholarship) -> list[str]:
    lines = [
        f"{index}. {item.published_date}",
        item.title,
    ]
    if item.eligibility_reason:
        lines.append(f"符合原因：{item.eligibility_reason}")
    lines.append(item.source_url)
    return lines
