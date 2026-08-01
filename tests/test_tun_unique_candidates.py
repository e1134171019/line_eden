# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.collectors.tun_program_watch_collector import (
    _extract_program_notices_with_counts,
)


def test_nested_dom_nodes_count_as_one_unique_candidate() -> None:
    program = ScholarshipProgramWatch(
        "energy",
        "能源工程獎學金",
        "測試基金會",
        ("能源工程獎學金",),
        "https://foundation.example/news",
        "verified",
    )
    html = """
    <article>
      <h2><a href="/news/88">能源工程獎學金開放申請</a></h2>
      <time datetime="2026-09-15">2026-09-15</time>
    </article>
    """

    records, raw_nodes, unique_counts = _extract_program_notices_with_counts(
        html,
        "https://foundation.example/news",
        "https://foundation.example/news",
        (program,),
    )

    assert raw_nodes >= 1
    assert len(records) == 1
    assert unique_counts == {"energy": 1}
    assert records[0].match_method == "exact_alias"
    assert records[0].match_score == 100
