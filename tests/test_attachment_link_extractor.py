# -*- coding: utf-8 -*-

from src.extractors.attachment_link_extractor import (
    extract_attachment_inventory,
    extract_attachment_links,
)


# 驗證只擷取公告正文中的支援附件，並優先處理資格辦法。
def test_extract_and_rank_supported_attachments() -> None:
    html = """
    <body>
      <div class="banner"><a href="/banner.pdf">橫幅資料.pdf</a></div>
      <div class="mpgdetail">
        <h2>能源獎學金</h2>
        <a href="/files/application.docx">獎學金申請表.docx</a>
        <a href="/files/rules.pdf">評選辦法暨推薦書.pdf</a>
        <a href="/files/legacy.doc">舊版申請表.doc</a>
      </div>
    </body>
    """

    links = extract_attachment_links(
        html,
        "https://activity.lhu.edu.tw/p/404-1051-1.php",
        "能源獎學金",
        max_count=2,
    )

    assert links == [
        "https://activity.lhu.edu.tw/files/rules.pdf",
        "https://activity.lhu.edu.tw/files/application.docx",
    ]
    assert all("banner.pdf" not in link for link in links)
    assert all("legacy.doc" not in link for link in links)


# 驗證相同附件網址只保留一次。
def test_attachment_links_are_deduplicated() -> None:
    html = """
    <main>
      <h1>一般獎學金</h1>
      <a href="/files/rules.pdf">申請辦法.pdf</a>
      <a href="/files/rules.pdf">再次下載申請辦法.pdf</a>
    </main>
    """

    links = extract_attachment_links(
        html,
        "https://example.com/news/1",
        "一般獎學金",
        max_count=3,
    )

    assert links == ["https://example.com/files/rules.pdf"]


# 驗證附件總數不會因最多解析數量而被截斷。
def test_inventory_reports_total_and_selected_count() -> None:
    html = """
    <article><h1>一般獎學金</h1>
      <a href="/a.pdf">資格辦法.pdf</a>
      <a href="/b.pdf">申請須知.pdf</a>
      <a href="/c.docx">申請表.docx</a>
      <a href="/d.pdf">推薦書.pdf</a>
    </article>
    """

    inventory = extract_attachment_inventory(
        html, "https://example.com/news/1", "一般獎學金", max_count=2,
    )

    assert inventory.discovered_count == 4
    assert len(inventory.selected_urls) == 2
