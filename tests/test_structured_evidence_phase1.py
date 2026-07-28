# -*- coding: utf-8 -*-

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import (
    ExtractedAttachment,
    RULES_STATUS_GENERIC_UNCONFIRMED,
    RULES_STATUS_RESOLVED,
)
from src.evaluators.attachment_requirement import detect_attachment_requirement
from src.evaluators.eligibility_evaluator import ELIGIBLE, REVIEW, EligibilityEvaluator
from src.extractors.attachment_content_classifier import (
    CONTENT_RULES,
    CONTENT_SUPPORTING_DOCUMENT,
    classify_attachment_content,
)
from src.extractors.attachment_link_extractor import (
    GENERIC_ATTACHMENT,
    AttachmentLinkInventory,
    classify_attachment_role,
    extract_attachment_inventory,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力電子", "能源"),
    )


def _item() -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        "能源工程獎學金",
        "2026-07-27",
        "https://example.com/item",
    )


def _fetcher() -> AnnouncementDetailFetcher:
    return AnnouncementDetailFetcher(10.0, "test", 3, 1024 * 1024, 10)


def test_generic_attachment_label_has_its_own_role() -> None:
    assert classify_attachment_role("附件一.pdf") == GENERIC_ATTACHMENT
    assert classify_attachment_role("檔案下載.pdf") == GENERIC_ATTACHMENT


def test_generic_attachment_is_ranked_before_application_form() -> None:
    html = """
    <article><h1>能源工程獎學金</h1>
      <a href="/form.docx">申請表.docx</a>
      <a href="/attachment.pdf">附件一.pdf</a>
    </article>
    """
    inventory = extract_attachment_inventory(
        html,
        "https://example.com/news/1",
        "能源工程獎學金",
        max_count=1,
    )
    assert inventory.selected_roles == (GENERIC_ATTACHMENT,)
    assert inventory.selected_labels == ("附件一.pdf",)


def test_attachment_requirement_detector_covers_broad_reference() -> None:
    result = detect_attachment_requirement(
        "相關助學金項目及內容，請參考附件，並於期限內提出申請。"
    )
    assert result.required is True
    assert "請參考附件" in result.evidence_text


def test_attachment_content_must_confirm_rules() -> None:
    rules = classify_attachment_content(
        "申請資格如下：限大專在校生，學業平均80分以上，電子工程相關科系可申請。",
        GENERIC_ATTACHMENT,
    )
    supporting = classify_attachment_content(
        "未領取其他獎學金切結書，申請人姓名、簽章。",
        GENERIC_ATTACHMENT,
    )
    assert rules == CONTENT_RULES
    assert supporting == CONTENT_SUPPORTING_DOCUMENT


def test_unconfirmed_rules_status_blocks_positive_match() -> None:
    detail = "大專院校在校生，電子工程相關科系，學業平均80分以上。"
    decision = EligibilityEvaluator().evaluate(
        _item(),
        detail,
        _profile(),
        rules_status=RULES_STATUS_GENERIC_UNCONFIRMED,
    )
    assert decision.status == REVIEW
    assert "尚未確認" in decision.reason_text()


def test_resolved_rules_status_can_use_positive_matches() -> None:
    detail = "申請對象為大專院校在校生，電子工程相關科系，學業平均80分以上。"
    decision = EligibilityEvaluator().evaluate(
        _item(),
        detail,
        _profile(),
        rules_status=RULES_STATUS_RESOLVED,
    )
    assert decision.status == ELIGIBLE


def test_content_confirmed_generic_attachment_resolves_rules() -> None:
    inventory = AttachmentLinkInventory(
        selected_urls=("https://example.com/attachment.pdf",),
        discovered_count=1,
        selected_roles=(GENERIC_ATTACHMENT,),
        selected_labels=("附件一.pdf",),
        discovered_generic_count=1,
    )
    attachment = ExtractedAttachment(
        requested_url="https://example.com/attachment.pdf",
        final_url="https://example.com/attachment.pdf",
        label="附件一.pdf",
        role_hint=GENERIC_ATTACHMENT,
        content_role=CONTENT_RULES,
        document_kind="pdf",
        status="success",
        text="申請資格限大專學生。",
    )
    status = _fetcher()._determine_rules_status(
        "相關內容請參考附件。",
        inventory,
        (attachment,),
    )
    assert status == RULES_STATUS_RESOLVED
