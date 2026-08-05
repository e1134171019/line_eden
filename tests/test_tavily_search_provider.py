# -*- coding: utf-8 -*-

import json

import httpx
import pytest

import src.discovery.tavily_search_provider as provider_module
from src.discovery.tavily_search_provider import TavilySearchProvider


def test_tavily_provider_uses_bearer_auth_and_parses_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "測試獎學金115年申請辦法",
                        "url": "https://foundation.example/rules",
                        "content": "主辦單位測試基金會",
                        "published_date": "2026-08-01",
                    }
                ]
            },
        )

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs: object) -> httpx.Client:
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(provider_module.httpx, "Client", client_factory)
    provider = TavilySearchProvider(
        "tvly-test",
        "https://api.tavily.com/search",
        10,
        "ScholarshipAgentTest/1.0",
    )

    hits = provider.search("測試獎學金 115 申請辦法", 30)

    assert captured["authorization"] == "Bearer tvly-test"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["max_results"] == 20
    assert payload["search_depth"] == "basic"
    assert hits[0].url == "https://foundation.example/rules"
    assert hits[0].published_date == "2026-08-01"


def test_tavily_provider_rejects_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"results": {}}))

    def client_factory(**kwargs: object) -> httpx.Client:
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(provider_module.httpx, "Client", client_factory)
    provider = TavilySearchProvider("key", "https://api.tavily.com/search", 10, "ua")

    with pytest.raises(ValueError, match="results 格式錯誤"):
        provider.search("test")
