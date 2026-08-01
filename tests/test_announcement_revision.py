# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
    RULES_STATUS_RESOLVED,
)
from src.models.scholarship import (
    Scholarship,
    build_announcement_id,
    normalize_source_url,
)


def _source(policy_hash: str = "policy-a") -> ResourceDiagnostic:
    return ResourceDiagnostic(
        role="source",
        requested_url="https://example.com/news/1",
        final_url="https://example.com/news/1",
        content_type="text/html",
        size_bytes=100,
        document_kind="html",
        status="success",
        text_length=20,
        extraction_policy_hash=policy_hash,
    )


def _attachment(text: str, url: str) -> ExtractedAttachment:
    return ExtractedAttachment(
        requested_url=url,
        final_url=url,
        label="申請辦法",
        role_hint="rules",
        content_role="scholarship_rules",
        document_kind="pdf",
        status="success",
        text=text,
    )


def test_announcement_id_ignores_listing_metadata_and_url_noise() -> None:
    first = Scholarship.from_raw(
        "LHU",
        "舊標題",
        "2026-07-01",
        "HTTPS://EXAMPLE.COM:443/news/1?b=2&a=1#top",
    )
    second = Scholarship.from_raw(
        "lhu",
        "更新後標題",
        "2026-08-01",
        "https://example.com/news/1?a=1&b=2",
    )

    assert first.announcement_id == second.announcement_id
    assert first.content_hash != second.content_hash
    assert first.announcement_id == build_announcement_id("lhu", second.source_url)


def test_source_url_normalizer_preserves_relative_and_malformed_urls() -> None:
    assert normalize_source_url("/news/1") == "/news/1"
    assert normalize_source_url("https://example.com:bad/news") == (
        "https://example.com:bad/news"
    )
    assert normalize_source_url("https://[2001:db8::1]:443/news#top") == (
        "https://[2001:db8::1]/news"
    )


def test_revision_hash_ignores_whitespace_attachment_order_and_policy() -> None:
    first = DetailFetchResult(
        text="正文",
        source=_source("policy-a"),
        attachments=tuple(),
        discovered_attachment_count=2,
        body_text="申請資格  限大專生",
        extracted_attachments=(
            _attachment("平均 80 分", "https://example.com/b.pdf"),
            _attachment("電子工程系", "https://example.com/a.pdf"),
        ),
        rules_status=RULES_STATUS_RESOLVED,
    )
    reformatted = DetailFetchResult(
        text="正文",
        source=_source("policy-b"),
        attachments=tuple(),
        discovered_attachment_count=2,
        body_text="  申請資格 限大專生 ",
        extracted_attachments=(
            _attachment("電子工程系", "https://example.com/a.pdf"),
            _attachment("平均 80 分", "https://example.com/b.pdf"),
        ),
        rules_status=RULES_STATUS_RESOLVED,
    )

    assert first.revision_hash == reformatted.revision_hash
    assert first.extraction_policy_hash != reformatted.extraction_policy_hash


def test_revision_hash_changes_when_body_or_attachment_content_changes() -> None:
    original = DetailFetchResult(
        "正文",
        _source(),
        tuple(),
        1,
        body_text="限大專生申請",
        extracted_attachments=(
            _attachment("平均 80 分", "https://example.com/rules.pdf"),
        ),
        rules_status=RULES_STATUS_RESOLVED,
    )
    changed_body = DetailFetchResult(
        "正文",
        _source(),
        tuple(),
        1,
        body_text="限研究生申請",
        extracted_attachments=original.extracted_attachments,
        rules_status=RULES_STATUS_RESOLVED,
    )
    changed_attachment = DetailFetchResult(
        "正文",
        _source(),
        tuple(),
        1,
        body_text=original.body_text,
        extracted_attachments=(
            _attachment("平均 90 分", "https://example.com/rules.pdf"),
        ),
        rules_status=RULES_STATUS_RESOLVED,
    )

    assert original.revision_hash != changed_body.revision_hash
    assert original.revision_hash != changed_attachment.revision_hash
