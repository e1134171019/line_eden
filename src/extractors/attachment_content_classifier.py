# -*- coding: utf-8 -*-

CONTENT_RULES = "scholarship_rules"
CONTENT_APPLICATION_FORM = "application_form"
CONTENT_SUPPORTING_DOCUMENT = "supporting_document"
CONTENT_OTHER = "other"
CONTENT_UNCERTAIN = "uncertain"

_RULE_HEADERS = (
    "申請資格",
    "申請對象",
    "資格條件",
    "申請條件",
    "申請辦法",
    "獎學金辦法",
    "獎助學金辦法",
    "評選辦法",
)
_REQUIREMENT_TERMS = (
    "學業",
    "操行",
    "成績",
    "排名",
    "年級",
    "科系",
    "學系",
    "系所",
    "日間部",
    "進修部",
    "在職",
    "戶籍",
    "低收入戶",
    "中低收入戶",
    "原住民",
    "截止",
)
_QUALIFICATION_ACTIONS = (
    "可申請",
    "得申請",
    "提出申請",
    "學生申請",
    "限",
    "不受理",
    "不得申請",
)
_FORM_FIELDS = (
    "申請人姓名",
    "姓名",
    "學號",
    "身分證字號",
    "聯絡電話",
    "簽章",
    "推薦人",
)
_SUPPORTING_TERMS = (
    "切結書",
    "聲明書",
    "同意書",
    "證明書",
    "名冊",
    "證明文件",
)


def classify_attachment_content(text: str, role_hint: str = "unknown") -> str:
    """以實際文字確認附件內容角色；資訊不足時維持 uncertain。"""
    normalized = " ".join(text.split())
    if not normalized:
        return CONTENT_UNCERTAIN

    if any(term in normalized for term in _SUPPORTING_TERMS):
        return CONTENT_SUPPORTING_DOCUMENT

    rule_headers = sum(term in normalized for term in _RULE_HEADERS)
    requirement_terms = sum(term in normalized for term in _REQUIREMENT_TERMS)
    qualification_actions = sum(term in normalized for term in _QUALIFICATION_ACTIONS)
    if rule_headers >= 1 and requirement_terms >= 2:
        return CONTENT_RULES

    form_fields = sum(term in normalized for term in _FORM_FIELDS)
    if form_fields >= 3:
        return CONTENT_APPLICATION_FORM

    if (
        role_hint == "rules"
        and requirement_terms >= 1
        and (rule_headers >= 1 or qualification_actions >= 1)
    ):
        return CONTENT_RULES

    return CONTENT_OTHER if len(normalized) >= 40 else CONTENT_UNCERTAIN
