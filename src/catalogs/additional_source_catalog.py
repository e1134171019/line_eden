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
    review_reason: str = ""


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
    AdditionalScholarshipSource(
        source_id="foxconn-scholarship-whale",
        display_name="鴻海教育基金會－鴻海獎學鯨",
        entry_url="https://www.foxconnfoundation.org/plan/scholar/university",
        allowed_hosts=("foxconnfoundation.org", "www.foxconnfoundation.org"),
        max_pages=2,
        entry_title="鴻海教育基金會鴻海獎學鯨",
    ),
    AdditionalScholarshipSource(
        source_id="pan-wen-yuan-scholarship",
        display_name="潘文淵文教基金會獎學金",
        entry_url="https://pan.itri.org.tw/Index",
        allowed_hosts=("pan.itri.org.tw",),
        max_pages=5,
        entry_title="潘文淵文教基金會獎學金",
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
    AdditionalScholarshipSource(
        source_id="ntut-scholarship-platform",
        display_name="國立臺北科技大學獎助學金平台",
        entry_url="https://scholarship.ntut.edu.tw/",
        allowed_hosts=("scholarship.ntut.edu.tw",),
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="utaipei-external-scholarships",
        display_name="臺北市立大學校外獎助學金",
        entry_url="https://service.utaipei.edu.tw/p/412-1034-63.php?Lang=zh-tw",
        allowed_hosts=("service.utaipei.edu.tw",),
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="mcu-external-scholarships",
        display_name="銘傳大學校外獎助學金",
        entry_url=(
            "https://student.mcu.edu.tw/home/"
            "%E5%AD%B8%E5%8B%99%E5%B0%88%E5%8D%80-2/"
            "%E5%B0%B1%E5%AD%B8%E8%A3%9C%E5%8A%A9%E6%8E%AA%E6%96%BD_"
            "%E6%A0%A1%E5%A4%96%E7%8D%8E%E5%8A%A9%E5%AD%B8%E9%87%91/"
        ),
        allowed_hosts=("student.mcu.edu.tw",),
        max_pages=5,
    ),
    AdditionalScholarshipSource(
        source_id="uch-external-scholarships",
        display_name="健行科技大學校外獎助學金",
        entry_url="https://budget.sa.uch.edu.tw/?locale=zh_tw",
        allowed_hosts=("budget.sa.uch.edu.tw",),
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
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="tut-external-scholarships",
        display_name="台南應用科技大學校外獎助學金",
        entry_url="https://club-stud.tut.edu.tw/p/403-1038-1402-1.php?Lang=zh-tw",
        allowed_hosts=("club-stud.tut.edu.tw",),
        max_pages=10,
    ),
    AdditionalScholarshipSource(
        source_id="ncut-external-scholarships",
        display_name="國立勤益科技大學校外獎助學金",
        entry_url="https://osca.ncut.edu.tw/p/403-1010-611-1.php?Lang=zh-tw",
        allowed_hosts=("osca.ncut.edu.tw",),
        max_pages=10,
        review_reason=(
            "2026年持續更新且第一頁包含多個仍在申請中的基金會、政府與工程類方案。"
        ),
    ),
    AdditionalScholarshipSource(
        source_id="nfu-scholarships",
        display_name="國立虎尾科技大學獎助學金公告",
        entry_url="https://www.nfu.edu.tw/zh_tw/ann/art",
        allowed_hosts=("nfu.edu.tw", "www.nfu.edu.tw"),
        max_pages=10,
        review_reason=(
            "2026年持續更新，公告正文含資格、金額與期限，並能補足科技及企業方案。"
        ),
    ),
    AdditionalScholarshipSource(
        source_id="niu-scholarships",
        display_name="國立宜蘭大學獎助學金專區",
        entry_url="https://niuosa.niu.edu.tw/p/412-1004-559.php",
        allowed_hosts=("niuosa.niu.edu.tw",),
        max_pages=10,
        review_reason=(
            "獎助學金專區有長期分頁與2026年近期公告，涵蓋一般、地方及基金會方案。"
        ),
    ),
    AdditionalScholarshipSource(
        source_id="ntut-ee-scholarships",
        display_name="國立臺北科技大學電機系獎助學金",
        entry_url="https://ee.ntut.edu.tw/p/403-1013-1598-1.php?Lang=zh-tw",
        allowed_hosts=("ee.ntut.edu.tw",),
        max_pages=5,
        review_reason=(
            "2026年持續發布電機、電網、科技企業與研究型獎學金，與使用者研究方向高度相關。"
        ),
    ),
)


ADDITIONAL_SCHOLARSHIP_SOURCES = (
    *OFFICIAL_ADDITIONAL_SOURCES,
    *BROAD_SCHOLARSHIP_PORTALS,
)
