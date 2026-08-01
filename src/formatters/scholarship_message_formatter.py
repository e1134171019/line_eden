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


# 建立每筆公告都包含獨立網址、硬性資格與人工確認項的 LINE 摘要。
def build_summary_message(
    items: list[Scholarship],
    batch_index: int,
    batch_count: int,
) -> str:
    lines = [f"【獎學金硬性資格篩選｜第 {batch_index}/{batch_count} 則】"]
    for index, item in enumerate(items, start=1):
        lines.extend(_build_item_lines(index, item))
    return "\n".join(lines)


# 建立單筆公告的日期、標題、硬性理由、人工確認項與正文連結。
def _build_item_lines(index: int, item: Scholarship) -> list[str]:
    lines = [
        f"{index}. {item.published_date or '日期未知'}",
        item.title,
    ]
    if item.eligibility_reason:
        label = "硬性條件符合" if item.eligibility_status == "eligible" else "待確認"
        lines.append(f"{label}：{item.eligibility_reason}")
    if item.review_kind:
        lines.append(f"待確認類型：{item.review_kind}")
    if item.manual_checks:
        lines.append("請自行確認：")
        lines.extend(f"- {_strip_manual_prefix(check)}" for check in item.manual_checks)
    lines.append(item.detail_url or item.source_url)
    return lines


def _strip_manual_prefix(value: str) -> str:
    prefix = "請自行確認："
    return value[len(prefix):].strip() if value.startswith(prefix) else value
