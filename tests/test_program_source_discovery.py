# -*- coding: utf-8 -*-

from src.discovery.program_query_builder import build_program_queries
from src.discovery.search_provider import SearchHit
from src.discovery.source_candidate_ranker import (
    SOURCE_OFFICIAL,
    SOURCE_SCHOOL,
    rank_source_candidates,
)
from src.discovery.source_discovery_service import (
    ProgramDiscoveryRequest,
    ProgramSourceDiscoveryService,
)
from src.discovery.source_identity_validator import (
    SOURCE_REJECTED,
    SOURCE_VERIFIED,
    validate_source_identity,
)


# 查詢必須同時涵蓋民國年、西元年、PDF與正式學校轉載。
def test_query_builder_covers_annual_and_attachment_paths() -> None:
    queries = build_program_queries(
        "測試獎學金",
        "測試基金會",
        ("測試助學金",),
        current_year=2026,
    )

    joined = "\n".join(queries)

    assert "115" in joined
    assert "2026" in joined
    assert "PDF" in joined
    assert "site:edu.tw" in joined
    assert "測試基金會" in joined


# 官方入口應高於學校轉載，純申請登入頁須降分。
def test_source_ranker_prefers_verified_discovery_paths() -> None:
    hits = [
        SearchHit(
            "測試獎學金115年申請辦法",
            "https://foundation.example/rules",
            "測試基金會申請資格",
        ),
        SearchHit(
            "測試獎學金115年公告",
            "https://osa.school.edu.tw/news/1",
            "測試基金會正式轉載",
        ),
        SearchHit(
            "測試獎學金登入",
            "https://foundation.example/apply/login",
            "測試基金會115年報名系統",
        ),
    ]

    ranked = rank_source_candidates(
        hits,
        "測試獎學金",
        "測試基金會",
        official_hosts=("foundation.example",),
        current_year=2026,
    )

    assert ranked[0].source_role == SOURCE_OFFICIAL
    assert ranked[0].hit.url.endswith("/rules")
    assert any(item.source_role == SOURCE_SCHOOL for item in ranked)
    assert ranked[-1].hit.url.endswith("/apply/login")


# 正式學校轉載須同時命中方案與主辦單位才可直接驗證。
def test_identity_validator_requires_program_and_organizer_for_relay() -> None:
    verified = validate_source_identity(
        "https://osa.school.edu.tw/news/1",
        "測試獎學金115年申請",
        "主辦單位：測試基金會。申請資格詳附件。",
        "測試獎學金",
        "測試基金會",
    )
    rejected = validate_source_identity(
        "https://osa.school.edu.tw/news/2",
        "名稱相近獎學金",
        "主辦單位：其他基金會。",
        "測試獎學金",
        "測試基金會",
    )

    assert verified.status == SOURCE_VERIFIED
    assert rejected.status == SOURCE_REJECTED


class _FakeSearchProvider:
    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        _ = query, limit
        return [
            SearchHit(
                "測試獎學金115年申請辦法",
                "https://foundation.example/rules",
                "測試基金會申請資格",
            )
        ]


# 發現服務應保留查詢 provenance，並依網址去除跨查詢重複結果。
def test_discovery_service_keeps_queries_and_deduplicates_hits() -> None:
    service = ProgramSourceDiscoveryService(_FakeSearchProvider())

    result = service.discover(
        ProgramDiscoveryRequest(
            "test-program",
            "測試獎學金",
            "測試基金會",
            official_hosts=("foundation.example",),
        ),
        current_year=2026,
    )

    assert result.program_id == "test-program"
    assert len(result.queries) >= 5
    assert len(result.candidates) == 1
    assert result.candidates[0].source_role == SOURCE_OFFICIAL
