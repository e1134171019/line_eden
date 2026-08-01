# -*- coding: utf-8 -*-

from src.extractors.announcement_content_extractor import extract_announcement_content


def test_auden_policy_extracts_full_application_content_without_navigation() -> None:
    html = """
    <html><body>
      <nav>首頁 關於基金會 歷年活動</nav>
      <article>
        <h1>2026耀登炳南大專院校優秀人才獎學金</h1>
        <div class="entry-content">
          <p>申請資格：國內大專院校大學生。</p>
          <p>資訊、通訊、生醫工程與環境永續相關系所可申請。</p>
          <p>申請日期至2026年9月30日。</p>
          <p>申請方式：線上報名並檢附申請文件。</p>
        </div>
      </article>
      <footer>聯絡我們 隱私權政策</footer>
    </body></html>
    """

    result = extract_announcement_content(
        html,
        "2026耀登炳南大專院校優秀人才獎學金",
        "https://www.auden.com.tw/2026scholarship/",
    )

    assert result.policy_name == "auden-html"
    assert result.selected_selector == ".entry-content"
    assert result.heuristic_fallback is False
    assert "資訊、通訊、生醫工程" in result.text
    assert "線上報名" in result.text
    assert "隱私權政策" not in result.text


def test_unknown_site_uses_versioned_default_policy() -> None:
    html = (
        "<main><h1>獎學金公告</h1>"
        "<p>申請資格為國內大專院校在校生，申請方式採線上報名並檢附文件。</p>"
        "</main>"
    )

    result = extract_announcement_content(
        html,
        "獎學金公告",
        "https://example.test/news/1",
    )

    assert result.policy_name == "default-html"
    assert result.policy_hash
    assert result.selected_selector == "main"
