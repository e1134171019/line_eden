# -*- coding: utf-8 -*-

from datetime import date


# 為單一方案建立官方、政府、學校轉載與附件搜尋查詢。
def build_program_queries(
    title: str,
    organizer: str,
    aliases: tuple[str, ...] = tuple(),
    *,
    current_year: int | None = None,
) -> tuple[str, ...]:
    year = current_year if current_year is not None else date.today().year
    roc_year = year - 1911
    names = tuple(dict.fromkeys((title, *aliases)))
    primary = names[:3]
    queries = [f'"{name}" {roc_year} 申請辦法' for name in primary]
    queries.extend(
        (
            f'"{title}" {year} PDF',
            f'"{organizer}" "{title}"',
            f'site:edu.tw "{title}" {roc_year}',
            f'site:gov.tw "{title}" {roc_year}',
            f'"{title}" 簡章 資格 附件',
        )
    )
    return tuple(dict.fromkeys(queries))
