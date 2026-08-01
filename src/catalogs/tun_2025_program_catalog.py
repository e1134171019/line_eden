# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum

TUN_DISCOVERY_URL = (
    "https://university.1111.com.tw/zone/university/"
    "discussTopic.asp?cat=University&id=354229"
)

OFFICIAL_VERIFIED = "verified"
OFFICIAL_PENDING = "pending"


class ProgramSourceType(StrEnum):
    """區分方案入口需要的抓取策略。"""

    LISTING = "listing"
    FIXED_PAGE = "fixed_page"
    DYNAMIC_PAGE = "dynamic_page"
    CORE_COVERED = "core_covered"


@dataclass(frozen=True)
class ScholarshipProgramWatch:
    """一項獎學金方案及其官方公告入口。"""

    program_id: str
    title: str
    organizer: str
    aliases: tuple[str, ...]
    official_url: str
    official_status: str
    source_type: ProgramSourceType = ProgramSourceType.LISTING


# TUN 僅用於發現名稱；資格、期限與公告正文必須回到官方入口。
TUN_2025_PROGRAMS: tuple[ScholarshipProgramWatch, ...] = (
    ScholarshipProgramWatch(
        "foxconn-scholarship-whale",
        "鴻海獎學鯨",
        "鴻海教育基金會",
        ("鴻海獎學鯨", "獎學鯨"),
        "https://www.foxconnfoundation.org/plan/scholar/university",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "avc-talented-student",
        "奇鋐教育基金會資優學生獎學金",
        "奇鋐教育基金會",
        ("奇鋐教育基金會資優學生獎學金", "奇鋐資優學生獎學金"),
        "https://www.avcgroup.org/Scholar",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "cfh-graduate",
        "鄭豐喜研究所獎學金",
        "鄭豐喜文化教育基金會",
        ("鄭豐喜研究所獎學金", "研究所獎學金"),
        "https://www.cfh.org.tw/?cat=9",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "cfh-university",
        "鄭豐喜大學獎學金",
        "鄭豐喜文化教育基金會",
        ("鄭豐喜大學獎學金", "大學獎學金"),
        "https://www.cfh.org.tw/?cat=9",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "tcb-foundation",
        "台中商業銀行文教基金會獎學金",
        "台中商業銀行文教基金會",
        ("台中商業銀行文教基金會獎學金", "台中商銀獎學金"),
        "https://www.tcbbank.com.tw/Intro/B_37_08.html",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "tainan-kaiji",
        "臺南市臺疆祖廟大學專科以上學校中低、低收入戶清寒優秀獎學金",
        "臺疆祖廟大觀音亭暨祀典興濟宮",
        ("臺疆祖廟清寒優秀獎學金", "臺疆祖廟獎學金"),
        "",
        OFFICIAL_PENDING,
    ),
    ScholarshipProgramWatch(
        "songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "台灣松樑教育公益促進協會",
        ("台灣松樑教育公益促進協會助學金", "松樑助學金"),
        "https://www.slceas.org.tw/index.php/scholarship",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "wang-yun-wu-self-study",
        "王雲五先生自學獎學金",
        "王雲五基金會",
        ("王雲五先生自學獎學金", "王雲五自學獎學金"),
        "https://yunwu.org.tw/y/news/category/6",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "rehe-association",
        "台北市熱河同鄉會獎助金",
        "台北市熱河同鄉會",
        ("台北市熱河同鄉會獎助金", "熱河同鄉會獎助金"),
        "https://zhao.org.tw/news",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "wisdomshare-service-learning",
        "青力親為●千萬祝福服務學習獎勵計畫",
        "天河教育基金會",
        ("青力親為", "千萬祝福服務學習獎勵計畫"),
        "https://www.wisdomshare.com.tw/index.php?action=news&cid=1",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "it-social-care",
        "資訊人社會關懷獎學金",
        "中華民國電腦學會",
        ("資訊人社會關懷獎學金",),
        "https://www.csroc.org.tw/news.jsp",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "you-care-hand-in-hand",
        "大手拉小手助學計畫",
        "普仁青年關懷基金會",
        ("大手拉小手助學計畫", "大手拉小手"),
        "https://www.you-care.org.tw/List.aspx?mid=34",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "chiu-filial-piety",
        "績優清寒孝親獎助學金",
        "邱創煥文教基金會",
        ("績優清寒孝親獎助學金", "清寒孝親獎助學金"),
        "",
        OFFICIAL_PENDING,
    ),
    ScholarshipProgramWatch(
        "buddha-charity-progress",
        "誌善清寒學生進步獎學金",
        "誌善文教基金會",
        ("誌善清寒學生進步獎學金", "清寒學生進步獎學金"),
        "https://www.buddha-charity.org/",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "yonglin-hope",
        "永齡銘日希望獎助學金",
        "永齡教育慈善基金會",
        ("永齡銘日希望獎助學金", "永齡希望獎助學金", "銘日希望獎助學金"),
        "https://edu.yonglin.org.tw/scholarship/",
        OFFICIAL_VERIFIED,
        ProgramSourceType.DYNAMIC_PAGE,
    ),
    ScholarshipProgramWatch(
        "ht-talented-long-term",
        "行天宮資優學生長期獎助學金",
        "行天宮五大志業",
        ("行天宮資優學生長期獎助學金", "資優學生長期獎助學金"),
        "https://www.ht.org.tw/religion177.htm",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "ht-student-aid",
        "行天宮助學金",
        "行天宮五大志業",
        ("行天宮助學金",),
        "https://www.ht.org.tw/religion153.htm",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "cht-fang-hsien-chi",
        "中華電信方賢齊先生獎學金",
        "中華電信基金會",
        ("中華電信方賢齊先生獎學金", "方賢齊先生獎學金"),
        "https://www.chtf.org.tw/project/693",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "heart-child",
        "心臟病童獎勵學金",
        "心臟病童相關公益組織",
        ("心臟病童獎勵學金",),
        "https://www.ccft.org.tw/List.aspx?tid=128",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "sunshine-scholarship",
        "陽光獎學金",
        "陽光社會福利基金會",
        ("陽光獎學金",),
        "https://scholarship.sunshine.org.tw/?cat=1",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "sunshine-wanzu",
        "萬足燒傷勞工子女大專生獎助學金",
        "陽光社會福利基金會",
        ("萬足燒傷勞工子女大專生獎助學金", "萬足獎助學金"),
        "https://scholarship.sunshine.org.tw/?cat=1",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "cfh-disabled-family",
        "鄭豐喜肢障者家庭子女獎學金",
        "鄭豐喜文化教育基金會",
        ("鄭豐喜肢障者家庭子女獎學金", "肢障者家庭子女獎學金"),
        "https://www.cfh.org.tw/?cat=9",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "dapeng-aid",
        "大鵬科技慈善基金會獎助學金",
        "大鵬科技慈善基金會",
        ("大鵬科技慈善基金會獎助學金", "大鵬獎助學金"),
        "",
        OFFICIAL_PENDING,
    ),
    ScholarshipProgramWatch(
        "hndasset-wenxiang",
        "文向獎學金",
        "文向教育基金會",
        ("文向獎學金",),
        "https://www.hndasset.com/csr-zh?lang=zh",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "cy-arch-aid",
        "昌益慈善基金會獎助學金",
        "昌益慈善基金會",
        ("昌益慈善基金會獎助學金", "昌益獎助學金"),
        "https://www.cy-arch.com.tw/foundation/scholarship",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "lihpao-fullon",
        "麗寶福容獎助學金",
        "麗寶文化藝術基金會",
        ("麗寶福容獎助學金",),
        "https://www.lihpao.org.tw/active_detail.php?no=95",
        OFFICIAL_VERIFIED,
        ProgramSourceType.FIXED_PAGE,
    ),
    ScholarshipProgramWatch(
        "gfc-scholarship",
        "崇友實業獎學金",
        "崇友文教基金會",
        ("崇友實業獎學金", "崇友獎學金"),
        "https://www.gfc.org.tw/news",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "auden-innovation-research",
        "耀登炳南創新研究獎",
        "耀登炳南教育基金會",
        ("耀登炳南創新研究獎", "炳南創新研究獎"),
        "https://www.auden.com.tw/news-4/",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "auden-university-talent",
        "耀登炳南大專校院優秀人才獎學金",
        "耀登炳南教育基金會",
        ("耀登炳南大專校院優秀人才獎學金", "大專校院優秀人才獎學金"),
        "https://www.auden.com.tw/news-4/",
        OFFICIAL_VERIFIED,
    ),
    ScholarshipProgramWatch(
        "harmony-stability",
        "和諧安定獎學金",
        "和諧安定相關公益組織",
        ("和諧安定獎學金",),
        "",
        OFFICIAL_PENDING,
    ),
)


def verified_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳已有可驗證官方入口的方案。"""

    return tuple(
        item for item in TUN_2025_PROGRAMS if item.official_status == OFFICIAL_VERIFIED
    )


def pending_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳尚未找到可靠官方公告入口的方案。"""

    return tuple(
        item for item in TUN_2025_PROGRAMS if item.official_status == OFFICIAL_PENDING
    )


def validate_catalog() -> None:
    """在測試與啟動時驗證 30 項目錄的最低資料契約。"""

    if len(TUN_2025_PROGRAMS) != 30:
        raise ValueError("TUN 方案目錄必須固定為 30 項。")
    ids = [item.program_id for item in TUN_2025_PROGRAMS]
    if len(ids) != len(set(ids)):
        raise ValueError("TUN 方案 program_id 不得重複。")
    for item in TUN_2025_PROGRAMS:
        if not item.title.strip() or not item.organizer.strip() or not item.aliases:
            raise ValueError(f"方案資料不完整：{item.program_id}")
        if item.official_status == OFFICIAL_VERIFIED and not item.official_url:
            raise ValueError(f"已驗證方案缺少官方網址：{item.program_id}")
        if item.official_status == OFFICIAL_PENDING and item.official_url:
            raise ValueError(f"待確認方案不得假裝已有官方網址：{item.program_id}")
        if "university.1111.com.tw" in item.official_url:
            raise ValueError("TUN 彙整頁不得作為正式公告來源。")


validate_catalog()
