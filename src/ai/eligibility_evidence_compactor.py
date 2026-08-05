# -*- coding: utf-8 -*-

from dataclasses import replace
import re

from src.diagnostics.detail_fetch_diagnostics import ExtractedAttachment, NoticeContent
from src.models.document_evidence import DocumentPageEvidence

MAX_COMPACTED_EVIDENCE_CHARS = 8000
_MAIN_TEXT_WITH_ATTACHMENTS_CHARS = 2000
_BLOCK_CHARS = 700
_CONTEXT_RADIUS = 1

_STRONG_MARKERS = (
    "申請資格", "甄試資格", "報名資格", "申請對象", "申請條件",
    "資格條件", "申請人資格", "申請人應", "應具備資格",
)
_QUALIFICATION_MARKERS = (
    "限於", "不得申請", "不予受理", "排除", "學位", "年級", "科系",
    "學系", "系所", "學院", "進修部", "日間部", "在職專班", "學業",
    "成績", "操行", "排名", "戶籍", "國籍", "身分", "低收入", "弱勢",
    "身心障礙", "申請期間", "報名期間", "截止", "應繳文件", "應備文件",
)
_CONTRACT_MARKERS = (
    "行政契約", "權利義務", "違約", "返國服務", "賠償責任", "契約終止",
)


def compact_notice_content(
    content: NoticeContent,
    max_chars: int = MAX_COMPACTED_EVIDENCE_CHARS,
) -> NoticeContent:
    """只保留正文與主要辦法中的資格相關段落，限制總文字量。"""
    if max_chars < 1:
        raise ValueError("資格證據字元上限必須大於 0")
    rules_attachments = tuple(
        item
        for item in content.attachments
        if item.status == "success"
        and item.content_role == "scholarship_rules"
        and item.text.strip()
    )
    if not rules_attachments:
        return NoticeContent(
            compact_eligibility_text(content.main_text, max_chars),
            tuple(),
            content.rules_status,
        )
    main_budget = min(_MAIN_TEXT_WITH_ATTACHMENTS_CHARS, max(1, max_chars // 3))
    main_text = compact_eligibility_text(content.main_text, main_budget)
    remaining = max(max_chars - len(main_text), 0)
    attachments: list[ExtractedAttachment] = []
    for index, item in enumerate(rules_attachments):
        if remaining < 1:
            break
        slots = len(rules_attachments) - index
        budget = max(1, remaining // slots)
        compacted = _compact_attachment(item, budget)
        attachments.append(compacted)
        remaining = max(remaining - len(compacted.text), 0)
    return NoticeContent(main_text, tuple(attachments), content.rules_status)


# 同步壓縮附件合併文字與逐頁文字，避免頁碼證據在模型輸入中遺失。
def _compact_attachment(
    attachment: ExtractedAttachment,
    max_chars: int,
) -> ExtractedAttachment:
    if not attachment.pages:
        text = compact_eligibility_text(attachment.text, max_chars)
        return replace(attachment, text=text)
    pages = _compact_pages(attachment.pages, max_chars)
    text = "\n".join(page.text for page in pages if page.text.strip())
    return replace(attachment, text=text, pages=pages)


# 將總字元預算平均分配到文件頁面。
def _compact_pages(
    pages: tuple[DocumentPageEvidence, ...],
    max_chars: int,
) -> tuple[DocumentPageEvidence, ...]:
    page_budget = max(1, max_chars // max(len(pages), 1))
    compacted = tuple(
        replace(page, text=compact_eligibility_text(page.text, page_budget))
        for page in pages
    )
    return tuple(page for page in compacted if page.text.strip())


def compact_eligibility_text(text: str, max_chars: int) -> str:
    """依資格訊號選取高價值段落及其相鄰內容，保留原始順序。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized or len(normalized) <= max_chars:
        return normalized
    blocks = _split_blocks(normalized)
    scores = [_block_score(block) for block in blocks]
    selected: set[int] = set(range(min(2, len(blocks))))
    ranked = sorted(
        (index for index, score in enumerate(scores) if score > 0),
        key=lambda index: (-scores[index], index),
    )
    for index in ranked:
        candidates = {
            candidate
            for candidate in range(index - _CONTEXT_RADIUS, index + _CONTEXT_RADIUS + 1)
            if 0 <= candidate < len(blocks)
        }
        proposed = selected | candidates
        if _selected_length(blocks, proposed) <= max_chars:
            selected = proposed
    if not any(score > 0 for score in scores):
        return normalized[:max_chars].rstrip()
    return _fit_selected_blocks(blocks, selected, max_chars)


def _split_blocks(text: str) -> list[str]:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    if len(paragraphs) < 3:
        paragraphs = [line.strip() for line in text.split("\n") if line.strip()]
    blocks: list[str] = []
    for paragraph in paragraphs:
        blocks.extend(
            paragraph[start : start + _BLOCK_CHARS]
            for start in range(0, len(paragraph), _BLOCK_CHARS)
        )
    return blocks or [text]


def _block_score(block: str) -> int:
    score = 8 * sum(marker in block for marker in _STRONG_MARKERS)
    score += 2 * sum(marker in block for marker in _QUALIFICATION_MARKERS)
    if not any(marker in block for marker in _STRONG_MARKERS):
        score -= 5 * sum(marker in block for marker in _CONTRACT_MARKERS)
    return score


def _selected_length(blocks: list[str], selected: set[int]) -> int:
    if not selected:
        return 0
    return sum(len(blocks[index]) for index in selected) + len(selected) - 1


def _fit_selected_blocks(
    blocks: list[str],
    selected: set[int],
    max_chars: int,
) -> str:
    output: list[str] = []
    remaining = max_chars
    for index in sorted(selected):
        separator = 1 if output else 0
        available = remaining - separator
        if available <= 0:
            break
        block = blocks[index]
        output.append(block[:available].rstrip())
        remaining -= separator + min(len(block), available)
        if len(block) > available:
            break
    return "\n".join(item for item in output if item)
