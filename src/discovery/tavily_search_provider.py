# -*- coding: utf-8 -*-

from typing import Any

import httpx

from src.discovery.search_provider import SearchHit


class TavilySearchProvider:
    """以 Tavily Search API 實作公開網路搜尋，不直接信任結果摘要。"""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        timeout_seconds: float,
        user_agent: str,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Tavily API key 不得為空白")
        self.api_key = api_key.strip()
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        if not query.strip():
            return []
        max_results = min(max(limit, 1), 20)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        payload = {
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        with httpx.Client(
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.post(self.endpoint, json=payload)
            response.raise_for_status()
        return _parse_search_hits(response.json())


def _parse_search_hits(payload: Any) -> list[SearchHit]:
    if not isinstance(payload, dict):
        raise ValueError("Tavily 搜尋回應不是 JSON object")
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        raise ValueError("Tavily 搜尋 results 格式錯誤")
    hits: list[SearchHit] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = _string(item.get("url"))
        if not url:
            continue
        hits.append(
            SearchHit(
                title=_string(item.get("title")),
                url=url,
                snippet=_string(item.get("content")),
                published_date=_string(item.get("published_date")),
            )
        )
    return hits


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
