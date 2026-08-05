# -*- coding: utf-8 -*-

from datetime import date

from src.evaluators.runtime_safety import (
    OPEN,
    STALE_UNKNOWN,
    classify_application_period,
    extract_application_deadline,
)
from src.extractors.attachment_link_extractor import (
    RULES,
    extract_attachment_inventory,
)


def test_verified_official_html_rules_page_is_selected() -> None:
    html = """
    <article>
      <h1>115學年度中華電信方賢齊先生獎學金</h1>
      <p>
        詳細申請辦法請至
        <a href="https://www.chtf.org.tw/project/693">
          https://www.chtf.org.tw/project/693
        </a>
      </p>
      <a href="https://www.chtf.org.tw/project/344">相關專案</a>
    </article>
    """

    inventory = extract_attachment_inventory(
        html,
        "https://www.chtf.org.tw/news/912",
        "115學年度中華電信方賢齊先生獎學金",
        3,
    )

    assert inventory.selected_urls == ("https://www.chtf.org.tw/project/693",)
    assert inventory.selected_roles == (RULES,)
    assert inventory.discovered_rules_count == 1


def test_undated_yearless_relay_is_never_projected_into_current_year() -> None:
    period = classify_application_period(
        "台北市熱河同鄉會獎助金申請日期：10月1日至10月31日止。",
        "",
        today=date(2026, 8, 5),
    )

    assert period.status == STALE_UNKNOWN
    assert period.deadline is None


def test_current_notice_ignores_older_cycle_dates_from_rules_page() -> None:
    text = (
        "115學年度獎學金申請期間：115年8月1日至115年10月6日止。"
        "固定方案頁仍保留114學年度申請截至114年10月17日止。"
    )

    deadline = extract_application_deadline(text, "2026-07-31")
    period = classify_application_period(text, "2026-07-31", today=date(2026, 8, 5))

    assert deadline == date(2026, 10, 6)
    assert period.status == OPEN
