# -*- coding: utf-8 -*-

from dataclasses import dataclass

from src.models.source_quality import SourceUrlType


@dataclass(frozen=True)
class LiveSourceCandidate:
    """經 production 驗證可作為主入口或回退入口的來源。"""

    url: str
    source_url_type: SourceUrlType
    reason: str


@dataclass(frozen=True)
class LiveProgramContract:
    """補充實際網站標題、穩定入口與強制替換策略。"""

    aliases: tuple[str, ...] = tuple()
    preferred_sources: tuple[LiveSourceCandidate, ...] = tuple()
    force_replace: bool = False


# 只放 production 已證實需要特殊 live 契約的方案。
LIVE_PROGRAM_CONTRACTS: dict[str, LiveProgramContract] = {
    "tf4dr-aid": LiveProgramContract(
        aliases=(
            "第1學期助學金",
            "第2學期助學金",
            "本會助學金",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://www.tf4dr.org/posts",
                SourceUrlType.LIST,
                "官方最新消息列表；實際年度標題常省略基金會名稱。",
            ),
        ),
    ),
    "hsinrong-emergency-aid": LiveProgramContract(
        aliases=(
            "竹山欣榮圖書館急難學生助學金",
            "欣榮圖書館急難學生助學金",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://osa.nfu.edu.tw/zh_tw/4/help",
                SourceUrlType.RELAY_LIST,
                "正式大學急難救助列表，實際名稱未使用『急難救助』完整詞組。",
            ),
        ),
    ),
    "lovepeace-disadvantaged": LiveProgramContract(
        aliases=(
            "祥和文教基金會獎助學金",
            "祥和文教基金會114年獎助學金",
            "財團法人祥和文教基金會獎助學金申請辦法",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://www.lovepeace.org.tw/Download.php?CataP=7&N_Key=192",
                SourceUrlType.LIST,
                "官方公文及表單列表，申請辦法標題未包含『優秀清寒』。",
            ),
        ),
    ),
    "buddha-charity-progress": LiveProgramContract(
        aliases=(
            "誌善清寒學生進步獎學金",
            "高中職專大碩誌善清寒學生進步獎學金",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://service.utaipei.edu.tw/p/404-1034-130714.php?Lang=zh-tw",
                SourceUrlType.RELAY_DETAIL,
                "115年正式大學轉載，含資格正文與附件入口。",
            ),
        ),
        force_replace=True,
    ),
    "yonglin-hope": LiveProgramContract(
        aliases=(
            "115年永齡銘日希望獎助學金",
            "永齡銘日希望獎助學金辦法",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://service.utaipei.edu.tw/p/404-1034-133653.php?Lang=zh-tw",
                SourceUrlType.RELAY_DETAIL,
                "115年正式大學轉載；官方方案站在 runner 發生憑證鏈錯誤。",
            ),
            LiveSourceCandidate(
                "https://osa.ndhu.edu.tw/p/406-1005-260310%2Cr402.php?Lang=zh-tw",
                SourceUrlType.RELAY_DETAIL,
                "115年第二個正式大學轉載備援。",
            ),
        ),
        force_replace=True,
    ),
    "sunshine-scholarship": LiveProgramContract(
        aliases=(
            "獎助學金申請說明",
            "陽光獎助學金",
            "陽光獎學金",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://scls.sunshine.org.tw/",
                SourceUrlType.EVERGREEN,
                "官方115年線上申請說明，使用可正常驗證的獨立子網域。",
            ),
            LiveSourceCandidate(
                "https://www.sunshine.org.tw/news/announce",
                SourceUrlType.LIST,
                "陽光基金會主站重要公告列表。",
            ),
        ),
        force_replace=True,
    ),
    "sunshine-wanzu": LiveProgramContract(
        aliases=(
            "萬足燒傷勞工子女大專生獎助學金",
            "萬足燒傷勞工子女大專生獎助學金申請",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://announce.yzu.edu.tw/index.php/tw/st/st-lgs20250828-1100-01",
                SourceUrlType.RELAY_DETAIL,
                "最近一期正式大學轉載，完整列出萬足方案資格。",
            ),
            LiveSourceCandidate(
                "https://www.sunshine.org.tw/news/announce",
                SourceUrlType.LIST,
                "陽光基金會主站重要公告列表。",
            ),
        ),
        force_replace=True,
    ),
    "dapeng-aid": LiveProgramContract(
        aliases=(
            "大鵬科技慈善基金會115年第一次獎助學金",
            "大鵬科技慈善基金會獎助學金",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://osa.ndhu.edu.tw/p/406-1005-254221%2Cr402.php?Lang=zh-tw",
                SourceUrlType.RELAY_DETAIL,
                "115年正式大學轉載，正文及附件皆可直接取得。",
            ),
            LiveSourceCandidate(
                "https://www.ntin.edu.tw/news_detail.aspx?id=50777",
                SourceUrlType.RELAY_DETAIL,
                "115年另一正式學校轉載備援。",
            ),
        ),
        force_replace=True,
    ),
    "songliang-aid": LiveProgramContract(
        aliases=(
            "助學金實施辦法",
            "松樑助學金實施辦法",
        ),
        preferred_sources=(
            LiveSourceCandidate(
                "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
                SourceUrlType.EVERGREEN,
                "官方助學金實施辦法；不得再以入口頁領域文字判定資格。",
            ),
        ),
        force_replace=True,
    ),
}


# 回傳方案的 production live 契約；未列入者使用一般來源契約。
def live_contract(program_id: str) -> LiveProgramContract:
    return LIVE_PROGRAM_CONTRACTS.get(program_id, LiveProgramContract())
