# -*- coding: utf-8 -*-

import re

APPLICATION = "application"
LOAN = "loan"
POLICY = "policy"
RESULT = "result"
INFORMATION = "information"
UNKNOWN = "unknown"

RESULT_MARKERS = (
    "獲獎名單",
    "錄取名單",
    "得獎名單",
    "核定名單",
    "結果公告",
    "得獎公告",
    "獲獎公告",
    "審核結果",
    "審查結果",
    "頒發名單",
    "正取名單",
    "備取名單",
)
POLICY_MARKERS = (
    "修正",
    "修訂",
    "條文",
    "法規",
    "作業要點",
    "函送",
    "廢止",
    "不適用",
)
APPLICATION_MARKERS = (
    "申請公告",
    "受理申請",
    "開放申請",
    "開始申請",
    "申辦公告",
    "申請資格",
    "申請對象",
    "申請期間",
    "申請方式",
    "截止日期",
    "檢附文件",
    "徵件",
    "報名",
)
INFORMATION_MARKERS = (
    "說明會",
    "注意事項",
    "相關事宜",
    "宣導",
    "提醒",
    "常見問題",
    "問答集",
    "FAQ",
)
AWARD_MARKERS = (
    "獎學金",
    "助學金",
    "獎助學金",
    "獎助金",
    "助學計畫",
    "獎勵學金",
    "濟助",
    "補助",
)


# 依標題與正文判斷公告是否為可申請獎助機會。
def classify_notice(title: str, detail_text: str) -> str:
    normalized_title = " ".join(title.split())
    normalized_text = " ".join(detail_text.split())
    if _contains_any(normalized_title, RESULT_MARKERS):
        return RESULT
    preclassified = pre_classify(normalized_title, normalized_text)
    if preclassified is not None:
        return preclassified
    if _is_policy_notice(normalized_title):
        return POLICY
    if _contains_any(normalized_title, INFORMATION_MARKERS):
        return INFORMATION
    if _is_loan_notice(normalized_title):
        return LOAN
    # 標題已明確寫申請／報名／徵件時，正文中的歷史結果或相關連結不得否決。
    if _contains_any(normalized_title, APPLICATION_MARKERS):
        return APPLICATION
    if _is_application_notice(normalized_title, normalized_text):
        return APPLICATION
    return UNKNOWN


# 快速排除作息、換算表、程序文件與尚待公布訊息，避免獎助關鍵字造成誤判。
def pre_classify(title: str, detail_text: str) -> str | None:
    text = f"{title} {detail_text[:200]}"
    if re.search(r"作息|行事曆|辦公時間|暑假|寒假", text):
        return INFORMATION
    if re.search(r"換算表|名額.{0,12}換算|排名.{0,12}換算", text):
        return POLICY
    if re.search(r"申辦流程|申請流程|作業流程|流程圖", text):
        return INFORMATION
    if re.search(r"說明會|座談會|宣導", text):
        return INFORMATION
    if re.search(r"(?:將於|預計).{0,24}(?:公布|公告|上線)|尚未公布", title):
        return INFORMATION
    if _is_standalone_contract(title):
        return INFORMATION
    return None


# 單獨契約書是獲獎後程序文件；同時包含甄試或申請簡章時仍視為申請公告。
def _is_standalone_contract(title: str) -> bool:
    if not re.search(r"(?:行政)?契約書", title):
        return False
    application_context = (
        "甄試簡章",
        "甄選簡章",
        "申請簡章",
        "申請公告",
        "受理申請",
        "開放申請",
        "徵件",
        "報名",
    )
    return not _contains_any(title, application_context)


# 判斷標題是否明確屬於法規、制度修正或適用範圍說明。
def _is_policy_notice(title: str) -> bool:
    if _contains_any(title, POLICY_MARKERS):
        return True
    return title.endswith("辦法") and not _contains_any(title, APPLICATION_MARKERS)


# 就學貸款申辦雖可操作，但不屬於獎助金通知範圍。
def _is_loan_notice(title: str) -> bool:
    return "就學貸款" in title and any(marker in title for marker in ("申辦", "申請"))


# 判斷正文是否具有當期獎助申請行動訊號。
def _is_application_notice(title: str, detail_text: str) -> bool:
    if _contains_any(detail_text, RESULT_MARKERS):
        return False
    if _contains_any(detail_text, APPLICATION_MARKERS):
        return True
    return _contains_any(title, AWARD_MARKERS)


# 判斷文字是否包含任一指定標記。
def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)