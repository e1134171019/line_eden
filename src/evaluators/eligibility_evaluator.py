# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

ELIGIBLE = "eligible"
REVIEW = "review"
INELIGIBLE = "ineligible"

EXCLUSIVE_MARKERS = r"(?:限|僅限|只限|申請對象(?:為|限於)?|申請資格(?:為|限於)?|資格限於)"
PREFERENCE_MARKERS = ("優先", "優先考量", "加分", "酌予優先", "不限")
SPECIAL_STATUS_KEYWORDS = (
    "原住民",
    "低收入戶",
    "中低收入戶",
    "身心障礙",
    "癌友家庭子女",
    "單親家庭",
    "清寒",
)
TAIWAN_REGIONS = (
    "基隆市",
    "臺北市",
    "台北市",
    "新北市",
    "桃園市",
    "新竹市",
    "新竹縣",
    "苗栗縣",
    "臺中市",
    "台中市",
    "彰化縣",
    "南投縣",
    "雲林縣",
    "嘉義市",
    "嘉義縣",
    "臺南市",
    "台南市",
    "高雄市",
    "屏東縣",
    "宜蘭縣",
    "花蓮縣",
    "臺東縣",
    "台東縣",
    "澎湖縣",
    "金門縣",
    "連江縣",
)


@dataclass(frozen=True)
class EligibilityDecision:
    """單筆公告對指定學生背景的資格判斷結果。"""

    status: str
    reasons: tuple[str, ...]

    # 將多個原因整理成可保存與顯示的文字。
    def reason_text(self) -> str:
        return "；".join(self.reasons)


class EligibilityEvaluator:
    """以公告文字與學生背景進行保守的規則式資格判斷。"""

    # 評估公告，明確不符時排除，條件未知時保留人工確認。
    def evaluate(
        self,
        scholarship: Scholarship,
        detail_text: str,
        profile: StudentProfile,
    ) -> EligibilityDecision:
        title = self._normalize(scholarship.title)
        text = self._normalize(f"{title}。{detail_text}")
        exclusions = self._find_exclusions(text, title, profile)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        unknowns = self._find_unknowns(text, profile)
        if unknowns:
            return EligibilityDecision(REVIEW, tuple(unknowns))
        matches = self._find_matches(text, profile)
        if matches:
            return EligibilityDecision(ELIGIBLE, tuple(matches))
        return EligibilityDecision(REVIEW, ("公告未提供足夠條件，暫不推播。",))

    # 收集學制、年級、身分、成績、排名與戶籍的不符合條件。
    def _find_exclusions(
        self,
        text: str,
        title: str,
        profile: StudentProfile,
    ) -> list[str]:
        reasons = self._check_program(text, title, profile)
        reasons.extend(self._check_degree_and_year(text, title, profile))
        reasons.extend(self._check_special_status(text, title, profile))
        reasons.extend(self._check_grade_thresholds(text, profile))
        reasons.extend(self._check_rank_requirement(text, profile))
        reasons.extend(self._check_residence_requirement(text, profile))
        return reasons

    # 收集因背景資料不足或資格藏在附件而無法確認的條件。
    def _find_unknowns(self, text: str, profile: StudentProfile) -> list[str]:
        reasons: list[str] = []
        if self._requires_eligibility_attachment(text):
            reasons.append("申請資格仍需參閱附件，暫不推播。")
        if self._extract_required_region(text) and not profile.residence:
            reasons.append("公告有戶籍限制，但 profile.json 未填居住地。")
        if self._extract_rank_requirement(text) and not self._has_rank_data(profile):
            reasons.append("公告有排名限制，但 profile.json 的排名資料不完整。")
        return reasons

    # 判斷日間部、進修部或在職身分的明確限制。
    def _check_program(
        self,
        text: str,
        title: str,
        profile: StudentProfile,
    ) -> list[str]:
        reasons: list[str] = []
        if "進修" in profile.program_type:
            if self._is_explicitly_excluded(text, ("進修部", "進修學制")):
                reasons.append("公告明確排除進修部。")
            elif self._group_is_exclusive(text, title, ("日間部",), ("進修部",)):
                reasons.append("公告限定日間部，與目前學制不符。")
        if profile.employed and self._is_explicitly_excluded(text, ("在職學生", "在職者")):
            reasons.append("公告明確排除在職學生。")
        return reasons

    # 判斷學位層級、新生或應屆畢業年級限制。
    def _check_degree_and_year(
        self,
        text: str,
        title: str,
        profile: StudentProfile,
    ) -> list[str]:
        reasons: list[str] = []
        graduate = ("研究生", "碩士班", "博士班", "碩博士")
        bachelor = ("大學生", "大學部", "學士班", "大專學生")
        if profile.degree_level == "學士" and self._group_is_exclusive(text, title, graduate, bachelor):
            reasons.append("公告限定研究所層級。")
        if self._group_is_exclusive(text, title, ("高中生", "高職生", "國中生", "國小生"), bachelor):
            reasons.append("公告限定非大專學制。")
        reasons.extend(self._check_year_terms(text, title, profile.year))
        return reasons

    # 判斷新生與應屆畢業生的明確年級限制。
    def _check_year_terms(self, text: str, title: str, year: int) -> list[str]:
        reasons: list[str] = []
        if year > 1 and self._term_is_required(text, title, ("新生", "大一")):
            reasons.append("公告限定新生或大一學生。")
        if year < 4 and self._term_is_required(text, title, ("應屆畢業生", "應屆畢業")):
            reasons.append("公告限定應屆畢業生。")
        return reasons

    # 判斷特定家庭或法定身分限制。
    def _check_special_status(
        self,
        text: str,
        title: str,
        profile: StudentProfile,
    ) -> list[str]:
        profile_statuses = set(profile.special_statuses)
        for keyword in SPECIAL_STATUS_KEYWORDS:
            if keyword in profile_statuses:
                continue
            if self._special_status_is_required(text, title, keyword):
                return [f"公告限定「{keyword}」身分。"]
        return []

    # 判斷特殊身分是必要資格或只是優先條件。
    def _special_status_is_required(self, text: str, title: str, keyword: str) -> bool:
        if keyword in title and not self._contains_preference(title):
            return True
        for sentence in self._sentences(text):
            if keyword not in sentence or self._contains_preference(sentence):
                continue
            pattern = rf"{EXCLUSIVE_MARKERS}.{{0,16}}{re.escape(keyword)}"
            if re.search(pattern, sentence):
                return True
        return False

    # 判斷學業與操行成績門檻。
    def _check_grade_thresholds(
        self,
        text: str,
        profile: StudentProfile,
    ) -> list[str]:
        reasons: list[str] = []
        average = self._extract_threshold(text, ("學業平均", "平均成績", "學業成績"))
        conduct = self._extract_threshold(text, ("操行成績", "操行"))
        if average is not None and profile.average_grade < average:
            reasons.append(f"學業平均未達 {average:g} 分門檻。")
        if conduct is not None and profile.conduct_grade < conduct:
            reasons.append(f"操行成績未達 {conduct:g} 分門檻。")
        return reasons

    # 判斷班級排名門檻。
    def _check_rank_requirement(
        self,
        text: str,
        profile: StudentProfile,
    ) -> list[str]:
        requirement = self._extract_rank_requirement(text)
        if not requirement or not self._has_rank_data(profile):
            return []
        mode, threshold = requirement
        if mode == "rank" and profile.class_rank > threshold:
            return [f"班級排名未達前 {int(threshold)} 名門檻。"]
        percentage = profile.class_rank / profile.class_size * 100
        if mode == "percent" and percentage > threshold:
            return [f"班級排名未達前 {threshold:g}% 門檻。"]
        return []

    # 判斷戶籍地限制。
    def _check_residence_requirement(
        self,
        text: str,
        profile: StudentProfile,
    ) -> list[str]:
        required_region = self._extract_required_region(text)
        if not required_region or not profile.residence:
            return []
        if self._same_region(required_region, profile.residence):
            return []
        return [f"公告限設籍於 {required_region}，與目前居住地不符。"]

    # 收集可確認符合的學校、科系、學制、成績、排名與戶籍條件。
    def _find_matches(self, text: str, profile: StudentProfile) -> list[str]:
        reasons: list[str] = []
        if profile.school and profile.school in text:
            reasons.append("公告適用學校與目前就讀學校相符。")
        if profile.department and profile.department in text:
            reasons.append("公告指定科系與目前科系相符。")
        reasons.extend(self._field_matches(text, profile))
        reasons.extend(self._requirement_matches(text, profile))
        if self._is_general_college_student_notice(text):
            reasons.append("公告適用一般大專在校生，未發現明確排除條件。")
        return reasons

    # 判斷電子、電機、電力與能源領域是否相符。
    def _field_matches(self, text: str, profile: StudentProfile) -> list[str]:
        keywords = set(profile.research_keywords) | {"電子", "電機", "電力", "能源"}
        if any(keyword and keyword in text for keyword in keywords):
            return ["公告領域與電子／電力相關背景相符。"]
        return []

    # 判斷已知成績、排名、戶籍與學制門檻是否符合。
    def _requirement_matches(self, text: str, profile: StudentProfile) -> list[str]:
        reasons: list[str] = []
        if self._met_grade_requirement(text, profile):
            reasons.append("學業或操行成績符合公告門檻。")
        if self._met_rank_requirement(text, profile):
            reasons.append("班級排名符合公告門檻。")
        if self._met_residence_requirement(text, profile):
            reasons.append("戶籍條件符合公告限制。")
        if "進修" in profile.program_type and "進修部" in text:
            reasons.append("公告明確包含進修部學生。")
        return reasons

    # 判斷已知成績門檻是否全部符合。
    def _met_grade_requirement(self, text: str, profile: StudentProfile) -> bool:
        average = self._extract_threshold(text, ("學業平均", "平均成績", "學業成績"))
        conduct = self._extract_threshold(text, ("操行成績", "操行"))
        checks = []
        if average is not None:
            checks.append(profile.average_grade >= average)
        if conduct is not None:
            checks.append(profile.conduct_grade >= conduct)
        return bool(checks) and all(checks)

    # 判斷排名門檻是否符合。
    def _met_rank_requirement(self, text: str, profile: StudentProfile) -> bool:
        requirement = self._extract_rank_requirement(text)
        if not requirement or not self._has_rank_data(profile):
            return False
        mode, threshold = requirement
        if mode == "rank":
            return profile.class_rank <= threshold
        return profile.class_rank / profile.class_size * 100 <= threshold

    # 判斷戶籍門檻是否符合。
    def _met_residence_requirement(self, text: str, profile: StudentProfile) -> bool:
        region = self._extract_required_region(text)
        return bool(region and profile.residence and self._same_region(region, profile.residence))

    # 判斷公告是否明確限定一組對象，並排除列舉多組可申請情況。
    def _group_is_exclusive(
        self,
        text: str,
        title: str,
        targets: tuple[str, ...],
        included_groups: tuple[str, ...],
    ) -> bool:
        if self._title_requires_group(title, targets, included_groups):
            return True
        for sentence in self._sentences(text):
            if not any(target in sentence for target in targets):
                continue
            if self._sentence_includes_groups(sentence, included_groups):
                continue
            if self._sentence_requires_group(sentence, targets):
                return True
        return False

    # 判斷標題本身是否代表特定對象專屬公告。
    def _title_requires_group(
        self,
        title: str,
        targets: tuple[str, ...],
        included_groups: tuple[str, ...],
    ) -> bool:
        if self._contains_preference(title):
            return False
        if any(group in title for group in included_groups):
            return False
        return any(target in title for target in targets) and any(
            term in title for term in ("獎學金", "助學金", "就學貸款", "補助")
        )

    # 判斷句子是否同時列出其他可申請對象。
    def _sentence_includes_groups(
        self,
        sentence: str,
        included_groups: tuple[str, ...],
    ) -> bool:
        if not any(group in sentence for group in included_groups):
            return False
        return not self._is_explicitly_excluded(sentence, included_groups)

    # 判斷句子是否以限制語氣指定目標族群。
    def _sentence_requires_group(self, sentence: str, targets: tuple[str, ...]) -> bool:
        target_pattern = "|".join(re.escape(target) for target in targets)
        prefix = rf"{EXCLUSIVE_MARKERS}.{{0,18}}(?:{target_pattern})"
        suffix = rf"(?:{target_pattern}).{{0,10}}(?:始得|方可|才可|可申請)"
        return bool(re.search(prefix, sentence) or re.search(suffix, sentence))

    # 判斷指定對象是否被公告明確排除。
    def _is_explicitly_excluded(self, text: str, terms: tuple[str, ...]) -> bool:
        term_pattern = "|".join(re.escape(term) for term in terms)
        prefix = rf"(?:不含|不包括|不受理|不接受|排除|不得為).{{0,10}}(?:{term_pattern})"
        suffix = rf"(?:{term_pattern}).{{0,10}}(?:不得申請|不予受理|不適用)"
        return bool(re.search(prefix, text) or re.search(suffix, text))

    # 判斷年級或身分詞是否為必要資格。
    def _term_is_required(self, text: str, title: str, terms: tuple[str, ...]) -> bool:
        if any(term in title for term in terms) and not self._contains_preference(title):
            return True
        return any(
            self._sentence_requires_group(sentence, terms)
            for sentence in self._sentences(text)
            if any(term in sentence for term in terms)
        )

    # 從公告文字擷取指定成績欄位的最低分數。
    def _extract_threshold(self, text: str, labels: tuple[str, ...]) -> float | None:
        label_pattern = "|".join(re.escape(label) for label in labels)
        score = r"(\d{1,3}(?:\.\d+)?)"
        patterns = (
            rf"(?:{label_pattern}).{{0,12}}?{score}\s*分?\s*(?:以上|或以上)",
            rf"(?:{label_pattern}).{{0,12}}?(?:不得低於|至少|須達|需達|達){score}\s*分?",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        return None

    # 從公告文字擷取班級排名門檻。
    def _extract_rank_requirement(self, text: str) -> tuple[str, float] | None:
        label = r"(?:班級排名|班排名|成績排名|學業排名)"
        percent = re.search(rf"{label}.{{0,10}}前\s*(\d+(?:\.\d+)?)\s*%", text)
        if percent:
            return "percent", float(percent.group(1))
        rank = re.search(rf"{label}.{{0,10}}前\s*(\d+)\s*名", text)
        if rank:
            return "rank", float(rank.group(1))
        return None

    # 從公告文字擷取明確戶籍限制。
    def _extract_required_region(self, text: str) -> str | None:
        for region in TAIWAN_REGIONS:
            escaped = re.escape(region)
            patterns = (
                rf"(?:限|須|需|必須).{{0,10}}(?:設籍|戶籍).{{0,10}}{escaped}",
                rf"(?:設籍|戶籍).{{0,10}}{escaped}.{{0,10}}(?:者|學生|居民)",
            )
            if any(re.search(pattern, text) for pattern in patterns):
                return region
        return None

    # 判斷公告是否把資格條件交由附件說明。
    def _requires_eligibility_attachment(self, text: str) -> bool:
        subject = r"(?:申請資格|資格條件|申請條件|申請對象)"
        reference = r"(?:詳見|請參閱|如|依).{0,6}(?:附件|附檔)"
        return bool(re.search(rf"{subject}.{{0,20}}{reference}", text))

    # 判斷公告是否適用一般大專在校生。
    def _is_general_college_student_notice(self, text: str) -> bool:
        terms = ("大專院校學生", "大專校院學生", "大專在校生", "大學生", "在校學生")
        return any(term in text for term in terms)

    # 判斷句子是否表達優先而非必要資格。
    def _contains_preference(self, text: str) -> bool:
        return any(marker in text for marker in PREFERENCE_MARKERS)

    # 判斷排名資料是否完整可計算。
    def _has_rank_data(self, profile: StudentProfile) -> bool:
        return profile.class_rank > 0 and profile.class_size > 0

    # 比較臺／台異體字後的戶籍地。
    def _same_region(self, required: str, residence: str) -> bool:
        normalize = lambda value: value.replace("臺", "台")
        return normalize(required) in normalize(residence)

    # 依標點切分句子，降低跨句關鍵字誤判。
    def _sentences(self, text: str) -> list[str]:
        return [sentence.strip() for sentence in re.split(r"[。；;\n]", text) if sentence.strip()]

    # 壓縮公告空白，避免換行影響關鍵字判斷。
    def _normalize(self, text: str) -> str:
        return " ".join(text.split())
