# -*- coding: utf-8 -*-

from src.extractors.attachment_link_extractor import RULES, extract_attachment_inventory


def test_lhu_whole_page_fallback_recovers_portal_attachment_block() -> None:
    html = """
    <html><body>
      <main>
        <section><div><div><div><div><div class="mcont">
          <h2>華嚴蓮社大專學生佛學慈孝獎學金</h2>
          <p>相關資訊請自行下載。</p>
        </div></div></div></div></div></section>
      </main>
      <div class="module-attachment">
        <a href="/app/index.php?Action=downloadfile&amp;file=huayan">
          115年第57屆華嚴蓮社大專學生佛學慈孝獎學金申請辦法.pdf
        </a>
      </div>
    </body></html>
    """

    inventory = extract_attachment_inventory(
        html,
        "https://activity.lhu.edu.tw/p/404-1051-37351.php?Lang=zh-tw",
        "華嚴蓮社大專學生佛學慈孝獎學金",
        max_count=3,
    )

    assert inventory.selected_urls == (
        "https://activity.lhu.edu.tw/app/index.php?Action=downloadfile&file=huayan",
    )
    assert inventory.selected_roles == (RULES,)
    assert inventory.discovered_rules_count == 1
