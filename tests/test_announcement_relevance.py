# -*- coding: utf-8 -*-

from src.extractors.announcement_relevance import content_matches_announcement


# 正文包含完整公告名稱時即視為同一公告。
def test_accepts_body_with_exact_title() -> None:
    assert content_matches_announcement(
        "王惕吾先生新聞獎學金",
        "王惕吾先生新聞獎學金申請資格與應備文件如下。",
    )


# 標題為獎助公告且正文具有申請訊號時可接受。
def test_accepts_application_document_without_repeating_title() -> None:
    assert content_matches_announcement(
        "能源工程獎學金",
        "大專院校在校生可申請，請於九月三十日前完成送件。",
    )


# 抓到人物介紹或其他活動頁時必須標記不相關。
def test_rejects_unrelated_landing_page() -> None:
    assert not content_matches_announcement(
        "王惕吾先生新聞獎學金",
        "看完逆轉騎士紀錄片，相信很多人有疑問為什麼選擇騎車環島。",
    )


# 空白正文不得被視為成功來源。
def test_rejects_empty_body() -> None:
    assert not content_matches_announcement("測試獎學金", "")
