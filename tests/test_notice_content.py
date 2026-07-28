# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    NoticeContent,
    ResourceDiagnostic,
    RULES_STATUS_RESOLVED,
)


def _attachment(content_role: str, text: str) -> ExtractedAttachment:
    return ExtractedAttachment(
        requested_url="https://example.com/file.pdf",
        final_url="https://example.com/file.pdf",
        label="附件一",
        role_hint="generic_attachment",
        content_role=content_role,
        document_kind="pdf",
        status="success",
        text=text,
    )


def test_notice_content_only_includes_confirmed_rules() -> None:
    content = NoticeContent(
        main_text="正文提到『附件內容』四個字，但不是分隔標記。",
        attachments=(
            _attachment("scholarship_rules", "申請資格限電子工程系。"),
            _attachment("application_form", "申請人姓名與學號。"),
        ),
        rules_status=RULES_STATUS_RESOLVED,
    )

    text = content.eligibility_text()

    assert "附件內容" in text
    assert "電子工程系" in text
    assert "申請人姓名" not in text


def test_detail_fetch_result_exposes_structured_notice_content() -> None:
    source = ResourceDiagnostic(
        "source",
        "https://example.com/notice",
        "https://example.com/notice",
        "text/html",
        100,
        "html",
        "success",
        20,
    )
    result = DetailFetchResult(
        text="legacy text",
        source=source,
        attachments=tuple(),
        discovered_attachment_count=1,
        body_text="公告正文",
        extracted_attachments=(
            _attachment("scholarship_rules", "學業平均80分以上。"),
        ),
        rules_status=RULES_STATUS_RESOLVED,
    )

    assert result.content.main_text == "公告正文"
    assert result.content.rules_status == RULES_STATUS_RESOLVED
    assert result.eligibility_text() == "公告正文\n學業平均80分以上。"
