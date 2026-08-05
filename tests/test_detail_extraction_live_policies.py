# -*- coding: utf-8 -*-

from src.extractors.announcement_content_extractor import extract_announcement_content


def test_yzu_policy_extracts_application_article_instead_of_navigation() -> None:
    html = """
    <html><body>
      <nav>行政單位 管理學院 學務處 最新消息</nav>
      <div class="item-page">
        <h1>資訊人社會關懷獎學金</h1>
        <p>申請對象：大專校院資訊、統計、公共行政及法律相關科系在學學生。</p>
        <p>申請時間：自115年9月16日起至10月31日止。</p>
        <p>申請方式：上網填報，並依系統欄位完成提案內容與證明文件上傳。</p>
      </div>
    </body></html>
    """

    result = extract_announcement_content(
        html,
        "資訊人社會關懷獎學金",
        "https://announce.yzu.edu.tw/index.php/tw/st/example",
    )

    assert result.policy_name == "yzu-announcement-html"
    assert result.selected_selector == ".item-page"
    assert "申請對象" in result.text
    assert "10月31日" in result.text
    assert "行政單位" not in result.text


def test_hsing_tian_policy_uses_full_body_when_site_has_no_article_selector() -> None:
    html = """
    <html><body>
      <nav>五大志業 慈善志業 網站導覽</nav>
      <div class="unrecognized-layout">
        <h1>急難濟助</h1>
        <p>濟助對象：因家庭經濟突逢變故而影響就學之大專院校學生。</p>
        <p>申請方式：由學校填具申請書並檢附相關文件後提出申請。</p>
        <p>申請條件：限急難變故發生日起六個月內進行申請。</p>
      </div>
    </body></html>
    """

    result = extract_announcement_content(
        html,
        "急難濟助",
        "https://www.ht.org.tw/p1_religion_5_24.htm",
    )

    assert result.policy_name == "ht-policy-html"
    assert result.selected_selector == "body"
    assert "濟助對象" in result.text
    assert "六個月內" in result.text
    assert "網站導覽" not in result.text
