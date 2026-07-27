# -*- coding: utf-8 -*-

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher


# 驗證公告內頁會移除腳本與樣式並保留可判斷文字。
def test_parse_detail_html_to_plain_text() -> None:
    fetcher = AnnouncementDetailFetcher(10.0, "ScholarshipAgentTest/1.0")
    html = """
    <html>
      <head><style>.hidden { display: none; }</style></head>
      <body>
        <script>ignore_me()</script>
        <main>申請對象為大專院校電子工程系在校生。</main>
      </body>
    </html>
    """

    text = fetcher._parse_text(html)

    assert "電子工程系" in text
    assert "ignore_me" not in text
    assert "display" not in text
