# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import date

from src.discovery.program_query_builder import build_program_queries
from src.discovery.search_provider import SearchHit, SearchProvider
from src.discovery.source_candidate_ranker import (
    RankedSourceCandidate,
    rank_source_candidates,
)


@dataclass(frozen=True)
class ProgramDiscoveryRequest:
    """一項方案進行公開網路來源發現所需的已知身分。"""

    program_id: str
    title: str
    organizer: str
    aliases: tuple[str, ...] = tuple()
    official_hosts: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class ProgramDiscoveryResult:
    """保留實際搜尋查詢及去重排序後的入口候選。"""

    program_id: str
    queries: tuple[str, ...]
    candidates: tuple[RankedSourceCandidate, ...]


class ProgramSourceDiscoveryService:
    """使用可替換 SearchProvider，產生可供後續頁面身分驗證的候選。"""

    def __init__(self, provider: SearchProvider, results_per_query: int = 10) -> None:
        if results_per_query < 1:
            raise ValueError("每組搜尋結果數必須大於 0")
        self.provider = provider
        self.results_per_query = results_per_query

    def discover(
        self,
        request: ProgramDiscoveryRequest,
        *,
        current_year: int | None = None,
    ) -> ProgramDiscoveryResult:
        year = current_year if current_year is not None else date.today().year
        queries = build_program_queries(
            request.title,
            request.organizer,
            request.aliases,
            current_year=year,
        )
        hits = self._search_queries(queries)
        ranked = rank_source_candidates(
            hits,
            request.title,
            request.organizer,
            request.aliases,
            request.official_hosts,
            current_year=year,
        )
        return ProgramDiscoveryResult(request.program_id, queries, ranked)

    # 同一網址只保留第一次發現結果，避免不同查詢重複提高候選權重。
    def _search_queries(self, queries: tuple[str, ...]) -> list[SearchHit]:
        unique: dict[str, SearchHit] = {}
        for query in queries:
            for hit in self.provider.search(query, self.results_per_query):
                if hit.url:
                    unique.setdefault(hit.url, hit)
        return list(unique.values())
