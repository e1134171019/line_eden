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
