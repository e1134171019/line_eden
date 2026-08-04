# -*- coding: utf-8 -*-

from dataclasses import replace

from src.catalogs.tun_live_contracts import live_contract
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    RULES_STATUS_DECLARED_MISSING,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
    RULES_STATUS_GENERIC_UNCONFIRMED,
    RULES_STATUS_RESOLVED,
    RULES_STATUS_UNKNOWN,
)
from src.extractors.attachment_content_classifier import CONTENT_RULES
from src.models.document_evidence import (
    DocumentPageEvidence,
    EXTRACTION_HTML_TEXT,
)
from src.models.scholarship import Scholarship

_REFERENCE_ELIGIBLE_RULE_STATUSES = frozenset(
    {
        RULES_STATUS_UNKNOWN,
        RULES_STATUS_DECLARED_MISSING,
        RULES_STATUS_DISCOVERED_UNRESOLVED,
        RULES_STATUS_GENERIC_UNCONFIRMED,
    }
)


class EvidenceDetailFetcher(AnnouncementDetailFetcher):
    """優先使用正文 URL，並以非候選規則頁補足固定資格證據。"""

    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        detail_url = scholarship.detail_url or scholarship.source_url
        resolved = (
            scholarship
            if scholarship.source_url == detail_url
            else replace(scholarship, source_url=detail_url)
        )
        result = super().fetch_with_diagnostics(resolved)
        normalized = replace(result, text=result.eligibility_text())
        return self._append_reference_evidence(resolved, normalized)

    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.fetch_with_diagnostics(scholarship).text

    # 固定規則頁不參與公告發現；僅在契約要求或辦法未解析時追加為規則證據。
    def _append_reference_evidence(
        self,
        scholarship: Scholarship,
        result: DetailFetchResult,
    ) -> DetailFetchResult:
        contract = live_contract(scholarship.program_id)
        should_fetch = contract.include_reference_evidence or (
            result.rules_status in _REFERENCE_ELIGIBLE_RULE_STATUSES
        )
        if (
            result.source.status != "success"
            or not should_fetch
            or not contract.reference_sources
        ):
            return result

        for candidate in contract.reference_sources:
            reference_item = replace(
                scholarship,
                source_url=candidate.url,
                detail_url=candidate.url,
            )
            reference = super().fetch_with_diagnostics(reference_item)
            evidence_text = reference.eligibility_text().strip()
            if reference.source.status != "success" or not evidence_text:
                continue
            diagnostic = replace(
                reference.source,
                role="attachment",
                attachment_role="rules",
                attachment_label="固定資格規則頁",
            )
            extracted = ExtractedAttachment(
                requested_url=diagnostic.requested_url,
                final_url=diagnostic.final_url,
                label=diagnostic.attachment_label,
                role_hint=diagnostic.attachment_role,
                content_role=CONTENT_RULES,
                document_kind=diagnostic.document_kind,
                status=diagnostic.status,
                text=evidence_text,
                error=diagnostic.error,
                document_hash=diagnostic.document_hash,
                pages=(
                    DocumentPageEvidence(
                        1,
                        evidence_text,
                        EXTRACTION_HTML_TEXT,
                    ),
                ),
                verification_status="parsed_reference_evidence",
            )
            merged = replace(
                result,
                attachments=(*result.attachments, diagnostic),
                discovered_attachment_count=result.discovered_attachment_count + 1,
                extracted_attachments=(*result.extracted_attachments, extracted),
                rules_status=RULES_STATUS_RESOLVED,
            )
            return replace(merged, text=merged.eligibility_text())
        return result
