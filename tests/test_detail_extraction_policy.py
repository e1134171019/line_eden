# -*- coding: utf-8 -*-

import pytest

from src.extractors.announcement_content_extractor import extract_announcement_content
from src.models.detail_extraction import (
    DetailExtractionPolicy,
    ExtractionMode,
    SourceExtractionPolicyRule,
    resolve_detail_extraction_policy,
)


def _strict_policy() -> DetailExtractionPolicy:
    return DetailExtractionPolicy(
        name="strict-example",
        version="v1",
        mode=ExtractionMode.STRICT_SELECTORS,
        include_selectors=(".notice-body",),
        subtractive_selectors=(".advertisement",),
        min_content_length=10,
    )


def test_strict_policy_extracts_only_configured_region_with_metadata() -> None:
    html = """
    <main>
      <div class="advertisement">不相關的熱門活動補助資訊</div>
      <div class="notice-body">申請資格限電子工程系在校學生。</div>
    </main>
    """

    result = extract_announcement_content(html, policy=_strict_policy())

    assert result.text == "申請資格限電子工程系在校學生。"
    assert result.selector_used == ".notice-body"
    assert result.used_fallback is False
    assert result.policy_name == "strict-example"
    assert len(result.policy_hash) == 64


def test_strict_policy_fails_closed_when_selector_is_missing() -> None:
    with pytest.raises(ValueError, match="正文 selector 未匹配"):
        extract_announcement_content(
            "<main>這裡雖然有足夠長的文字，但不是設定的正文區域。</main>",
            policy=_strict_policy(),
        )


def test_policy_resolver_prefers_longest_matching_hostname_suffix() -> None:
    default = _strict_policy()
    school = DetailExtractionPolicy(
        "school",
        "v1",
        ExtractionMode.AUTO,
        ("main",),
        tuple(),
        10,
    )
    department = DetailExtractionPolicy(
        "department",
        "v2",
        ExtractionMode.PREFER_SELECTORS,
        ("article",),
        tuple(),
        10,
    )
    rules = (
        SourceExtractionPolicyRule("example.edu.tw", school),
        SourceExtractionPolicyRule("ee.example.edu.tw", department),
    )

    selected = resolve_detail_extraction_policy(
        "https://news.ee.example.edu.tw/posts/1",
        rules,
        default,
    )

    assert selected is department
