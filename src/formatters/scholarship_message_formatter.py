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


# LINE 僅顯示符合資格的公告名稱與正文連結。
def build_summary_message(
    items: list[Scholarship],
    batch_index: int,
    batch_count: int,
) -> str:
    lines = [f"【符合資格獎學金｜第 {batch_index}/{batch_count} 則】"]
    for index, item in enumerate(items, start=1):
        lines.extend(
            (
                f"{index}. {item.title}",
                item.detail_url or item.source_url,
            )
        )
    return "\n".join(lines)
