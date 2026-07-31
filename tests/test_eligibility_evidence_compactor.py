# -*- coding: utf-8 -*-

from src.ai.eligibility_evidence_compactor import (
    MAX_COMPACTED_EVIDENCE_CHARS,
    compact_eligibility_text,
    compact_notice_content,
)
from src.diagnostics.detail_fetch_diagnostics import ExtractedAttachment, NoticeContent


def _attachment(label: str, role: str, text: str) -> ExtractedAttachment:
    return ExtractedAttachment(
        requested_url=f"https://example.com/{label}",
        final_url=f"https://example.com/{label}",
        label=label,
        role_hint="rules",
        content_role=role,
        document_kind="pdf",
        status="success",
        text=text,
    )


def test_compacts_long_document_and_keeps_qualification_section() -> None:
    contract = "行政契約權利義務、違約與返國服務規定。" * 900
    qualification = (
        "申請資格：申請人須為大專院校學士班學生，"
        "學業平均八十分以上，且不得為進修部學生。"
    )
    text = f"留學獎學金甄試簡章\n\n{contract}\n\n{qualification}\n\n{contract}"

    compacted = compact_eligibility_text(text, MAX_COMPACTED_EVIDENCE_CHARS)

    assert len(compacted) <= MAX_COMPACTED_EVIDENCE_CHARS
    assert qualification in compacted
    assert len(compacted) < len(text)


def test_notice_compaction_keeps_only_confirmed_rules_attachments() -> None:
    rules = _attachment(
        "rules.pdf",
        "scholarship_rules",
        "申請資格：電子工程系學生，學業平均八十分以上。" * 300,
    )
    form = _attachment(
        "form.pdf",
        "application_form",
        "申請表姓名地址簽名欄位。" * 300,
    )
    content = NoticeContent(
        "公告正文：請依簡章提出申請。",
        (rules, form),
        "resolved",
    )

    compacted = compact_notice_content(content)

    assert len(compacted.attachments) == 1
    assert compacted.attachments[0].content_role == "scholarship_rules"
    assert "申請資格" in compacted.attachments[0].text
    total_length = len(compacted.main_text) + sum(
        len(item.text) for item in compacted.attachments
    )
    assert total_length <= MAX_COMPACTED_EVIDENCE_CHARS
