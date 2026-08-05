# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchHit:
    """搜尋供應商回傳的最小公開網路結果。"""

    title: str
    url: str
    snippet: str = ""
    published_date: str = ""


class SearchProvider(Protocol):
    """可替換的搜尋介面，不把 collector 綁死在單一外部服務。"""

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        ...
