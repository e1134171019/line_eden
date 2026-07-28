# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

PURPOSE_ELIGIBILITY_RULES = "eligibility_rules"
PURPOSE_APPLICATION_DETAILS = "application_details"
PURPOSE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class AttachmentRequirement:
    """公告正文對附件的依賴判斷與原文證據。"""

    required: bool
    purpose: str = PURPOSE_UNKNOWN
    evidence_text: str = ""


def detect_attachment_requirement(text: str) -> AttachmentRequirement:
    """統一判斷正文是否明示資格或申請資訊位於附件。"""
    normalized = " ".join(text.split())
    if not normalized:
        return AttachmentRequirement(False)

    qualification_subject = (
        r"(?:申請資格|詳細資格|資格條件|申請條件|申請對象|申請辦法)"
    )
    reference = (
        r"(?:詳見|請參閱|請參考|請見|如|依|下載).{0,10}"
        r"(?:附件|附檔|檔案|文件)"
    )
    match = re.search(rf"{qualification_subject}.{{0,30}}{reference}", normalized)
    if match:
        return AttachmentRequirement(
            True,
            PURPOSE_ELIGIBILITY_RULES,
            match.group(0),
        )

    detail_subject = (
        r"(?:相關資訊|相關內容|詳細內容|詳情|申請方式|"
        r"相關助學金項目及內容|各項資格)"
    )
    match = re.search(rf"{detail_subject}.{{0,24}}{reference}", normalized)
    if match:
        return AttachmentRequirement(
            True,
            PURPOSE_APPLICATION_DETAILS,
            match.group(0),
        )

    broad = re.search(
        r"(?:請參考附件|請參閱附件|詳見附件|內容請見附件|"
        r"詳情請見附件|請下載附件|如附件所示|依附件規定)",
        normalized,
    )
    if broad:
        return AttachmentRequirement(True, PURPOSE_UNKNOWN, broad.group(0))

    return AttachmentRequirement(False)
