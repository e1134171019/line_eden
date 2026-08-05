# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass(frozen=True)
class AdditionalScholarshipSource:
    """可直接監測的官方方案頁或高更新率校外獎助公告入口。"""

    source_id: str
    display_name: str
    entry_url: str
    allowed_hosts: tuple[str, ...]
    max_pages: int = 10
    entry_title: str = ""


OFFICIAL_ADDITIONAL_SOURCES: tuple[AdditionalScholarshipSource, ...] = (
    AdditionalScholarshipSource(
        source_id="tp2e-awards",
        display_name="台灣電力與能源工程協會",
        entry_url="https://tp2e.org/category/bulletin/news/events-news/",
        allowed_hosts=("tp2e.org",),
        max_pages=5,
    ),
    AdditionalScholarshipSource(
        source_id="ctci-technology-scholarship",
        display_name="中技社科技獎學金",
        entry_url=(
            "https://www.ctci.org.tw/8838/talent/ctci-scholarship/46612/46765/"
        ),
        allowed_hosts=("ctci.org.tw", "www.ctci.org.tw"),
        max_pages=2,
        entry_title="中技社科技獎學金",
    ),
)


BROAD_SCHOLARSHIP_PORTALS: tuple[AdditionalScholarshipSource, ...] = (
    AdditionalScholarshipSource(
        source_id="nutc-external-scholarships",
        display_name="國立臺中科技大學校外獎學金",
        entry_url="https://student.nutc.edu.tw/p/403-1020-34-1.php?Lang=zh-tw",
        allowed_hosts=("student.nutc.edu.tw",),
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="ncnu-external-scholarships",
        display_name="國立暨南國際大學校外獎助學金",
        entry_url="https://assistance.ncnu.edu.tw/p/403-1079-249-1.php?Lang=zh-tw",
        allowed_hosts=("assistance.ncnu.edu.tw",),
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="nptu-external-scholarships",
        display_name="國立屏東大學校外獎助學金",
        entry_url="https://staf-life.nptu.edu.tw/p/403-1074-3893-1.php?Lang=zh-tw",
        allowed_hosts=("staf-life.nptu.edu.tw",),
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="hku-external-scholarships",
        display_name="弘光科技大學校外獎助學金",
        entry_url=(
            "https://lf.hk.edu.tw/category/"
            "%E6%A0%A1%E5%A4%96%E7%8D%8E%E5%8A%A9%E5%AD%B8%E9%87%91"
            "%E6%9C%80%E6%96%B0%E5%85%AC%E5%91%8A/"
        ),
        allowed_hosts=("lf.hk.edu.tw",),
        max_pages=10,
    ),
)


ADDITIONAL_SCHOLARSHIP_SOURCES = (
    *OFFICIAL_ADDITIONAL_SOURCES,
    *BROAD_SCHOLARSHIP_PORTALS,
)
