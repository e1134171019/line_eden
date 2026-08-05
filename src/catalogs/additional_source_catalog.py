# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass(frozen=True)
class AdditionalScholarshipSource:
    """通過實際產出、更新性、穩定性與重複度審查的獎學金來源。"""

    source_id: str
    display_name: str
    entry_url: str
    allowed_hosts: tuple[str, ...]
    review_reason: str
    max_pages: int = 10
    entry_title: str = ""


OFFICIAL_ADDITIONAL_SOURCES: tuple[AdditionalScholarshipSource, ...] = (
    AdditionalScholarshipSource(
        source_id="tp2e-awards",
        display_name="台灣電力與能源工程協會",
        entry_url="https://tp2e.org/category/bulletin/news/events-news/",
        allowed_hosts=("tp2e.org",),
        review_reason="電力與能源專業官方來源，與使用者研究方向高度相關。",
        max_pages=5,
    ),
    AdditionalScholarshipSource(
        source_id="ctci-technology-scholarship",
        display_name="中技社科技獎學金",
        entry_url=(
            "https://www.ctci.org.tw/8838/talent/ctci-scholarship/46612/46765/"
        ),
        allowed_hosts=("ctci.org.tw", "www.ctci.org.tw"),
        review_reason="科技類官方獎學金，適合工程、研究與作品型申請者。",
        max_pages=2,
        entry_title="中技社科技獎學金",
    ),
    AdditionalScholarshipSource(
        source_id="pan-wen-yuan-scholarship",
        display_name="潘文淵文教基金會科技獎學金與獎項",
        entry_url=(
            "https://pan.itri.org.tw/datalist?"
            "MmmID=1310651426072512600&SiteID=1"
        ),
        allowed_hosts=("pan.itri.org.tw",),
        review_reason="半導體、電子、資訊與物聯網官方來源，與使用者技術方向高度相關。",
        max_pages=10,
    ),
)


BROAD_SCHOLARSHIP_PORTALS: tuple[AdditionalScholarshipSource, ...] = (
    AdditionalScholarshipSource(
        source_id="nutc-external-scholarships",
        display_name="國立臺中科技大學校外獎學金",
        entry_url="https://student.nutc.edu.tw/p/403-1020-34-1.php?Lang=zh-tw",
        allowed_hosts=("student.nutc.edu.tw",),
        review_reason="高更新率校外獎學金入口，能發現多個基金會與科技類方案。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="ncnu-external-scholarships",
        display_name="國立暨南國際大學校外獎助學金",
        entry_url="https://assistance.ncnu.edu.tw/p/403-1079-249-1.php?Lang=zh-tw",
        allowed_hosts=("assistance.ncnu.edu.tw",),
        review_reason="結構穩定且持續更新的校外獎助學金入口。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="nptu-external-scholarships",
        display_name="國立屏東大學校外獎助學金",
        entry_url="https://staf-life.nptu.edu.tw/p/403-1074-3893-1.php?Lang=zh-tw",
        allowed_hosts=("staf-life.nptu.edu.tw",),
        review_reason="能穩定產出多項校外方案，且公告格式適合自動解析。",
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
        review_reason="歷史與近期公告量充足，可補足基金會及地方型方案。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="ntut-scholarship-platform",
        display_name="國立臺北科技大學校外獎學金",
        entry_url="https://scholarship.ntut.edu.tw/p/412-1043-13135.php",
        allowed_hosts=("scholarship.ntut.edu.tw",),
        review_reason="目前持續更新校外方案，且是使用者未來升學目標學校。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="utaipei-external-scholarships",
        display_name="臺北市立大學校外獎助學金",
        entry_url="https://service.utaipei.edu.tw/p/412-1034-63.php?Lang=zh-tw",
        allowed_hosts=("service.utaipei.edu.tw",),
        review_reason="實際稽核產出量高，並持續發布跨地區校外獎助方案。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="uch-external-scholarships",
        display_name="健行科技大學校外獎助學金",
        entry_url="https://budget.sa.uch.edu.tw/?locale=zh_tw",
        allowed_hosts=("budget.sa.uch.edu.tw",),
        review_reason="實際稽核可穩定解析多筆校外方案，與既有來源互補。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="npu-scholarship-portal",
        display_name="國立澎湖科技大學獎助學金公告",
        entry_url=(
            "https://www.npu.edu.tw/sub/latestevent/index.aspx?"
            "Parser=9%2C22%2C501%2C486"
        ),
        allowed_hosts=("npu.edu.tw", "www.npu.edu.tw"),
        review_reason="實際稽核產出量高，能補足大量地方與基金會方案。",
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="tut-external-scholarships",
        display_name="台南應用科技大學校外獎助學金",
        entry_url="https://stud.tut.edu.tw/p/422-1007-1030.php?Lang=zh-tw",
        allowed_hosts=("stud.tut.edu.tw",),
        review_reason="官方校外專區持續更新，近期含多項科技與一般獎助方案。",
        max_pages=10,
    ),
)


ADDITIONAL_SCHOLARSHIP_SOURCES = (
    *OFFICIAL_ADDITIONAL_SOURCES,
    *BROAD_SCHOLARSHIP_PORTALS,
)
