# -*- coding: utf-8 -*-

import pytest

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_NOT_REQUIRED
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityEvaluator,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 使用已確認沒有經濟弱勢或其他特殊身分的目前學生背景。
def _profile() -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部四技",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.6,
        conduct_grade=86.0,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電機", "電力", "能源"),
        nationality="中華民國",
        enrollment_status="在學",
        academic_year_average=90.34,
        latest_semester_average=90.6,
        latest_conduct_grade=86.0,
        latest_class_rank=1,
        latest_class_size=17,
        has_failed_courses=False,
        has_major_discipline=False,
        special_statuses_confirmed=True,
    )


# 建立不含期限判斷的人工核對公告。
def _scholarship(program_id: str, title: str) -> Scholarship:
    return Scholarship.from_raw(
        source=f"golden-{program_id}",
        title=title,
        published_date="",
        source_url=f"https://example.test/{program_id}",
        program_id=program_id,
        entry_url=f"https://example.test/{program_id}",
        detail_url=f"https://example.test/{program_id}/detail",
    )


GOLDEN_CASES = (
    (
        "auden-university-talent",
        "2026耀登炳南大專院校優秀人才獎學金",
        "申請對象：具有中華民國國籍或外籍人士在台灣學校就讀者。"
        "就讀國內已立案大專院校資通訊、生醫工程及環境永續相關系所之"
        "學士班、碩士班及博士班在學學生，不含學士班一年級新生、休學生、"
        "延畢生、學分班及空中大學學生。學士班平均85分以上且系所排名前10%，"
        "無不及格科目，操行80分以上。",
        ELIGIBLE,
    ),
    (
        "cfh-university",
        "鄭豐喜研究所暨大學獎學金",
        "申請對象限國內研究所或大學在學之身心障礙學生。",
        INELIGIBLE,
    ),
    (
        "avc-talented-student",
        "奇鋐教育基金會資優學生獎學金",
        "申請對象限國小高年級、國中及高中資優學生，須由學校推薦。",
        INELIGIBLE,
    ),
    (
        "songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "申請對象為國內大專院校電子、電機相關科系學生，不含夜間部、"
        "推廣教育部、進修部及空中大學；家庭年所得60萬元以下且確有清寒"
        "或家庭變故事實。",
        INELIGIBLE,
    ),
    (
        "sunshine-scholarship",
        "陽光獎助學金",
        "申請對象須為燒燙傷或顱顏患者，或陽光傷友子女。",
        INELIGIBLE,
    ),
    (
        "tf4dr-aid",
        "賑災基金會助學金",
        "申請對象須為申請日前三年內重大天然災害受災家庭子女，並具低收入戶"
        "或中低收入戶身分。",
        INELIGIBLE,
    ),
    (
        "lijin-taoyuan",
        "利晉基金會清寒獎助學金",
        "申請資格限家境清寒學生。",
        INELIGIBLE,
    ),
    (
        "cht-fang-hsien-chi",
        "中華電信方賢齊先生獎學金",
        "全國公私立大專院校在學生，各學院各科系均可申請；低收入戶學生"
        "優先考量，學業優秀者亦可提出申請。",
        ELIGIBLE,
    ),
    (
        "heart-child",
        "心臟病童獎勵學金",
        "申請對象為曾於本基金會合約醫院接受心臟導管或外科手術治療的"
        "心臟病童。",
        INELIGIBLE,
    ),
    (
        "gfc-scholarship",
        "崇友實業獎學金",
        "日間部或進修部電子、電機相關科系學生均可申請；申請者須符合低收入戶、"
        "中低收入戶、清寒或家庭經濟失依其中一項。",
        INELIGIBLE,
    ),
    (
        "foxconn-scholarship-whale",
        "2026鴻海獎學鯨大專校院組獎學金",
        "申請資格\n"
        "(一)有學籍之日間部、進修學士班、碩士班、博士班，於修業年限內之學生。\n"
        "(二)前一學年度學業總成績平均70分以上，操行成績平均75分以上。\n"
        "(三)家庭經濟狀況或特殊狀況，符合下列條件其中之一者：\n"
        "家境清寒之邊緣戶。\n"
        "家庭突遭變故、家長非自願性失業或特殊情形致家庭經濟困難者。\n"
        "中低收入戶或低收入戶。\n"
        "接受特殊境遇家庭扶助者。",
        INELIGIBLE,
    ),
    (
        "cfh-graduate",
        "鄭豐喜研究所獎學金",
        "申請資格：國內研究所肢體障礙在學學生。",
        INELIGIBLE,
    ),
    (
        "kumota-flying",
        "雲田乘風飛揚獎助學金",
        "申請資格\n"
        "一、共同申請條件\n"
        "(一)具中華民國國籍，並設籍臺中市滿六個月以上。\n"
        "(二)家庭經濟弱勢，且經學校、社會福利單位或相關機關證明屬實。\n"
        "(三)前一學年度各學期學業成績平均達75分以上。\n"
        "二、大專院校組：國內高等教育深耕計畫受補助學校之在學學生。",
        INELIGIBLE,
    ),
    (
        "tcb-foundation",
        "台中商業銀行文教基金會大專院校獎助學金",
        "申請資格\n"
        "(一)國內大學日間部優秀學生。\n"
        "(二)上、下學期學業成績平均80分以上且無任何一科不及格。\n"
        "(三)申請人符合下列各款情形之一者：\n"
        "父母兄姐均失業或失去怙恃，家境困難、經濟拮据。\n"
        "父母兄姐雖服務於公司機關，但收入不足維持家庭生活。\n"
        "父母兄姐為人幫傭或設攤販，收入不足以維持生活。",
        INELIGIBLE,
    ),
    (
        "tainan-kaiji",
        "臺疆祖廟中低低收入戶清寒優秀獎學金",
        "申請條件：公私立大學在學學生，不含夜間部、進修學士、推廣教育及"
        "在職專班；在大臺南市設籍半年以上；須為中低收入戶或低收入戶子弟。",
        INELIGIBLE,
    ),
    (
        "wang-yun-wu-self-study",
        "王雲五先生自學獎學金",
        "補助對象：本獎學金以鼓勵大學院校學生為主。申請者應提出自學計畫書，"
        "計畫項目須為文、史、哲學等相關課題。",
        ELIGIBLE,
    ),
    (
        "rehe-association",
        "台北市熱河同鄉會獎助金",
        "申請資格：海外來台就讀國內公私立大學及研究所學生，已在台就讀一年以上，"
        "且學生父親或母親之祖籍符合國民政府熱河省建置。",
        INELIGIBLE,
    ),
    (
        "wisdomshare-service-learning",
        "2026青力親為・千萬祝福服務學習獎勵計畫",
        "申請資格（以下三點皆需符合）：\n"
        "(一)民國85年1月1日後出生之國內大專院校在校生及畢業生。\n"
        "(二)於114年第2學期含前任一學期曾申請就學貸款者。\n"
        "(三)114年11月1日至115年9月30日前曾擔任本計畫合作社福單位之志工。",
        REVIEW,
    ),
    (
        "hsinrong-emergency-aid",
        "欣榮圖書館急難學生助學金",
        "助學對象：限設籍於南投縣、雲林縣及彰化縣指定鄉鎮市之在學學生，"
        "且有父母雙亡、父母一方死亡或離棄、天災、意外、重病、父母離婚等變故，"
        "致無力繳納學雜費而影響繼續就學者。",
        INELIGIBLE,
    ),
    (
        "it-social-care",
        "資訊人社會關懷獎學金",
        "申請對象：大專校院資訊、統計、公共行政及法律等相關科系含研究所之在學學生，"
        "提案內容須具有資訊管理、資訊政策或資訊應用。",
        INELIGIBLE,
    ),
    (
        "you-care-hand-in-hand",
        "大手拉小手育成計畫",
        "申請對象為家庭經濟困難之高中、大專院校在學學生；不含在職專班及產學合作班。"
        "前一學年度學業成績70分以上，操行80分以上。",
        INELIGIBLE,
    ),
    (
        "chiu-filial-piety",
        "邱創煥文教基金會績優清寒孝親獎助學金",
        "申請對象限公私立國小五、六年級、國中及高中職學生，"
        "不含五專、夜校及補校，並須具清寒與孝親事蹟。",
        INELIGIBLE,
    ),
    (
        "buddha-charity-progress",
        "誌善清寒學生進步獎學金",
        "申請對象為高中職專、大、碩之清寒弱勢在學學生，"
        "須具有善、孝精神且學業進步、堅忍向上。",
        INELIGIBLE,
    ),
    (
        "cdf-vocational",
        "中華開發技藝職能獎學金",
        "申請資格為25歲以下高中職或大專院校在學學生，具藝術、體育或技職專長；"
        "技職專長不包含外語類、商業與管理類、電機電子資訊類。",
        INELIGIBLE,
    ),
)


@pytest.mark.parametrize(
    ("program_id", "title", "body", "expected_status"),
    GOLDEN_CASES,
)
def test_manual_source_golden_eligibility(
    program_id: str,
    title: str,
    body: str,
    expected_status: str,
) -> None:
    decision = EligibilityEvaluator().evaluate(
        _scholarship(program_id, title),
        body,
        _profile(),
        rules_status=RULES_STATUS_NOT_REQUIRED,
    )

    assert decision.status == expected_status, (
        program_id,
        decision.status,
        decision.reasons,
    )