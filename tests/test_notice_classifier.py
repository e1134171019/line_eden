# -*- coding: utf-8 -*-

from src.evaluators.notice_classifier import (
    APPLICATION,
    INFORMATION,
    LOAN,
    POLICY,
    RESULT,
    UNKNOWN,
    classify_notice,
)


# 驗證獎學金申請公告會進入個人資格判斷。
def test_classifies_scholarship_application() -> None:
    kind = classify_notice(
        "台灣電力與能源工程協會獎學金",
        "大專院校在校生可申請，截止日期為九月三十日。",
    )

    assert kind == APPLICATION


# 驗證就學貸款申辦公告會獨立分類，不混入獎助金通知。
def test_classifies_loan_application() -> None:
    kind = classify_notice("日間部學生就學貸款申辦公告", "請於期限內完成申辦。")

    assert kind == LOAN


# 驗證條文修正不會被當成可申請機會。
def test_classifies_policy_revision() -> None:
    kind = classify_notice("就學貸款作業要點部分條文修正案", "公告修正條文內容。")

    assert kind == POLICY


# 驗證獲獎名單不會被當成可申請機會。
def test_classifies_award_result() -> None:
    kind = classify_notice("優秀學生獎學金獲獎名單", "公布本次獲獎學生。")

    assert kind == RESULT


# 驗證一般說明會公告會分類為資訊型。
def test_classifies_information_notice() -> None:
    kind = classify_notice("就學貸款申辦說明會", "歡迎同學參加說明會。")

    assert kind == INFORMATION


# 驗證沒有足夠訊號的公告採 unknown。
def test_classifies_unknown_notice() -> None:
    kind = classify_notice("轉知相關消息", "詳細內容請參閱網站。")

    assert kind == UNKNOWN
