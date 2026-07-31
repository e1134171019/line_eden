# -*- coding: utf-8 -*-

from src.collectors.helpdreams_collector import HelpDreamsCollector


# 圓夢網第三欄是截止日，Scholarship.published_date 必須保持空白。
def test_helpdreams_parser_keeps_deadline_out_of_published_date() -> None:
    html = """
    <table>
      <tr>
        <th>獎學金名稱</th><th>機關單位名稱</th><th>申請期間(迄)</th>
      </tr>
      <tr>
        <td><a href="/helpdreams/Grants_Content.aspx?n=A&s=1">育秧獎助學金</a></td>
        <td>育田基金會</td>
        <td>115-09-20</td>
      </tr>
      <tr>
        <td><a href="/helpdreams/Grants_Content.aspx?n=A&s=2">資訊人獎學金</a></td>
        <td>電腦學會</td>
        <td>115-10-31</td>
      </tr>
    </table>
    """
    collector = HelpDreamsCollector(
        "moe-helpdreams-private",
        "教育部圓夢助學網－民間團體",
        "https://www.edu.tw/helpdreams/Grants.aspx?n=A",
        10.0,
        "test",
    )

    records = collector._parse_html(html)

    assert len(records) == 2
    assert records[0].published_date == ""
    assert records[0].source_url.endswith("Grants_Content.aspx?n=A&s=1")
    assert records[1].published_date == ""
