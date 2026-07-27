# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

EXCLUSIVE_WORDS = r"(?:限|僅限|只限|申請對象(?:為|限於)?|申請資格(?:為|限於)?|資格限於)"
PREFERENCE_WORDS = ("優先", "優先考量", "加分", "酌予優先", "不限")
SPECIAL_STATUSES = (
    "原住民",
    "低收入戶",
    "中低收入戶",
    "身心障礙",
    "癌友家庭子女",
    "單親家庭",
    "清寒",
)
TAIWAN_REGIONS = (
    "基隆市", "臺北市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣",
    "苗栗縣", "臺中市", "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市",
    "嘉義縣", "臺南市", "台南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣",
    "臺東縣", "台東縣", "澎湖縣", "金門縣", "連江縣",
)


# 壓縮公告空白，避免換行影響規則比對。
def normalize_text(text: str) -> str:
    return " ".join(text.split())


# 收集明確不符合的資格原因。
def find_exclusions(text: str, title: str, profile: StudentProfile) -> list[str]:
    reasons = _check_program(text, title, profile)
    reasons.extend(_check_degree(text, title, profile))
    reasons.extend(_check_year(text, title, profile))
    reasons.extend(_check_special_status(text, title, profile))
    reasons.extend(_check_grades(text, profile))
    reasons.extend(_check_rank(text, profile))
    reasons.extend(_check_residence(text, profile))
    return reasons


# 收集無法可靠確認的資格原因。
def find_unknowns(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if _requires_attachment(text):
        reasons.append("申請資格仍需參閱附件，暫不推播。")
    if _extract_region(text) and not profile.residence:
        reasons.append("公告有戶籍限制，但 profile.json 未填居住地。")
    if _extract_rank(text) and not _has_rank(profile):
        reasons.append("公告有排名限制，但 profile.json 的排名資料不完整。")
    return reasons


# 收集可確認符合的條件。
def find_matches(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if profile.school and profile.school in text:
        reasons.append("公告適用學校與目前就讀學校相符。")
    if profile.department and profile.department in text:
        reasons.append("公告指定科系與目前科系相符。")
    reasons.extend(_field_matches(text, profile))
    reasons.extend(_requirement_matches(text, profile))
    if _is_general_college_notice(text):
        reasons.append("公告適用一般大專在校生，未發現明確排除條件。")
    return reasons


# 判斷學制與在職身分限制。
def _check_program(text: str, title: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if "進修" in profile.program_type:
        if _explicitly_excludes(text, ("進修部", "進修學制")):
            reasons.append("公告明確排除進修部。")
        elif _group_is_exclusive(text, title, ("日間部",), ("進修部", "進修學制")):
            reasons.append("公告限定日間部，與目前學制不符。")
    if profile.employed and _explicitly_excludes(text, ("在職學生", "在職者")):
        reasons.append("公告明確排除在職學生。")
    return reasons


# 判斷學位層級限制。
def _check_degree(text: str, title: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    bachelor = ("大學生", "大學部", "學士班", "大專學生", "大專在校生")
    graduate = ("研究生", "碩士班", "博士班", "碩博士")
    if profile.degree_level == "學士" and _group_is_exclusive(text, title, graduate, bachelor):
        reasons.append("公告限定研究所層級。")
    school = ("高中生", "高職生", "國中生", "國小生")
    if _group_is_exclusive(text, title, school, bachelor):
        reasons.append("公告限定非大專學制。")
    return reasons


# 判斷新生與應屆畢業生限制。
def _check_year(text: str, title: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if profile.year > 1 and _term_is_required(text, title, ("新生", "大一")):
        reasons.append("公告限定新生或大一學生。")
    if profile.year < 4 and _term_is_required(text, title, ("應屆畢業生", "應屆畢業")):
        reasons.append("公告限定應屆畢業生。")
    return reasons


# 判斷特殊家庭或法定身分限制。
def _check_special_status(text: str, title: str, profile: StudentProfile) -> list[str]:
    owned = set(profile.special_statuses)
    for keyword in SPECIAL_STATUSES:
        if keyword not in owned and _special_status_is_required(text, title, keyword):
            return [f"公告限定「{keyword}」身分。"]
    return []


# 判斷特殊身分是必要條件或僅為優先條件。
def _special_status_is_required(text: str, title: str, keyword: str) -> bool:
    if keyword in title and not _contains_preference(title):
        return True
    for sentence in _sentences(text):
        if keyword not in sentence or _contains_preference(sentence):
            continue
        if re.search(rf"{EXCLUSIVE_WORDS}.{{0,16}}{re.escape(keyword)}", sentence):
            return True
    return False


# 判斷學業與操行成績門檻。
def _check_grades(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    average = _extract_score(text, ("學業平均", "平均成績", "學業成績"))
    conduct = _extract_score(text, ("操行成績", "操行"))
    if average is not None and profile.average_grade < average:
        reasons.append(f"學業平均未達 {average:g} 分門檻。")
    if conduct is not None and profile.conduct_grade < conduct:
        reasons.append(f"操行成績未達 {conduct:g} 分門檻。")
    return reasons


# 判斷班級排名門檻。
def _check_rank(text: str, profile: StudentProfile) -> list[str]:
    requirement = _extract_rank(text)
    if not requirement or not _has_rank(profile):
        return []
    mode, threshold = requirement
    if mode == "rank" and profile.class_rank > threshold:
        return [f"班級排名未達前 {int(threshold)} 名門檻。"]
    percentage = profile.class_rank / profile.class_size * 100
    if mode == "percent" and percentage > threshold:
        return [f"班級排名未達前 {threshold:g}% 門檻。"]
    return []


# 判斷戶籍地限制。
def _check_residence(text: str, profile: StudentProfile) -> list[str]:
    required = _extract_region(text)
    if not required or not profile.residence or _same_region(required, profile.residence):
        return []
    return [f"公告限設籍於 {required}，與目前居住地不符。"]


# 判斷電子、電機、電力與能源領域是否相符。
def _field_matches(text: str, profile: StudentProfile) -> list[str]:
    keywords = set(profile.research_keywords) | {"電子", "電機", "電力", "能源"}
    if any(keyword and keyword in text for keyword in keywords):
        return ["公告領域與電子／電力相關背景相符。"]
    return []


# 判斷成績、排名、戶籍與學制條件是否符合。
def _requirement_matches(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if _meets_scores(text, profile):
        reasons.append("學業或操行成績符合公告門檻。")
    if _meets_rank(text, profile):
        reasons.append("班級排名符合公告門檻。")
    if _meets_residence(text, profile):
        reasons.append("戶籍條件符合公告限制。")
    if "進修" in profile.program_type and "進修部" in text:
        reasons.append("公告明確包含進修部學生。")
    return reasons


# 判斷已知成績門檻是否全部符合。
def _meets_scores(text: str, profile: StudentProfile) -> bool:
    average = _extract_score(text, ("學業平均", "平均成績", "學業成績"))
    conduct = _extract_score(text, ("操行成績", "操行"))
    checks: list[bool] = []
    if average is not None:
        checks.append(profile.average_grade >= average)
    if conduct is not None:
        checks.append(profile.conduct_grade >= conduct)
    return bool(checks) and all(checks)


# 判斷排名門檻是否符合。
def _meets_rank(text: str, profile: StudentProfile) -> bool:
    requirement = _extract_rank(text)
    if not requirement or not _has_rank(profile):
        return False
    mode, threshold = requirement
    if mode == "rank":
        return profile.class_rank <= threshold
    return profile.class_rank / profile.class_size * 100 <= threshold


# 判斷戶籍門檻是否符合。
def _meets_residence(text: str, profile: StudentProfile) -> bool:
    region = _extract_region(text)
    return bool(region and profile.residence and _same_region(region, profile.residence))


# 判斷公告是否明確限定某組對象。
def _group_is_exclusive(
    text: str,
    title: str,
    targets: tuple[str, ...],
    included: tuple[str, ...],
) -> bool:
    if _title_requires_group(title, targets, included):
        return True
    for sentence in _sentences(text):
        if not any(target in sentence for target in targets):
            continue
        if _sentence_includes_groups(sentence, included):
            continue
        if _sentence_requires_group(sentence, targets):
            return True
    return False


# 判斷標題是否代表特定對象專屬公告。
def _title_requires_group(
    title: str,
    targets: tuple[str, ...],
    included: tuple[str, ...],
) -> bool:
    if _contains_preference(title) or any(group in title for group in included):
        return False
    awards = ("獎學金", "助學金", "就學貸款", "補助")
    return any(target in title for target in targets) and any(word in title for word in awards)


# 判斷句子是否同時列出其他可申請對象。
def _sentence_includes_groups(sentence: str, groups: tuple[str, ...]) -> bool:
    if not any(group in sentence for group in groups):
        return False
    return not _explicitly_excludes(sentence, groups)


# 判斷句子是否以限制語氣指定目標族群。
def _sentence_requires_group(sentence: str, targets: tuple[str, ...]) -> bool:
    pattern = "|".join(re.escape(target) for target in targets)
    prefix = rf"{EXCLUSIVE_WORDS}.{{0,18}}(?:{pattern})"
    suffix = rf"(?:{pattern}).{{0,10}}(?:始得|方可|才可|可申請)"
    return bool(re.search(prefix, sentence) or re.search(suffix, sentence))


# 判斷指定對象是否被公告明確排除。
def _explicitly_excludes(text: str, terms: tuple[str, ...]) -> bool:
    pattern = "|".join(re.escape(term) for term in terms)
    prefix = rf"(?:不含|不包括|不受理|不接受|排除|不得為).{{0,10}}(?:{pattern})"
    suffix = rf"(?:{pattern}).{{0,10}}(?:不得申請|不予受理|不適用)"
    return bool(re.search(prefix, text) or re.search(suffix, text))


# 判斷年級或身分詞是否為必要資格。
def _term_is_required(text: str, title: str, terms: tuple[str, ...]) -> bool:
    if any(term in title for term in terms) and not _contains_preference(title):
        return True
    return any(
        _sentence_requires_group(sentence, terms)
        for sentence in _sentences(text)
        if any(term in sentence for term in terms)
    )


# 從公告文字擷取最低分數。
def _extract_score(text: str, labels: tuple[str, ...]) -> float | None:
    label = "|".join(re.escape(item) for item in labels)
    score = r"(\d{1,3}(?:\.\d+)?)"
    patterns = (
        rf"(?:{label}).{{0,12}}?{score}\s*分?\s*(?:以上|或以上)",
        rf"(?:{label}).{{0,12}}?(?:不得低於|至少|須達|需達|達){score}\s*分?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


# 從公告文字擷取班級排名門檻。
def _extract_rank(text: str) -> tuple[str, float] | None:
    label = r"(?:班級排名|班排名|成績排名|學業排名)"
    percent = re.search(rf"{label}.{{0,10}}前\s*(\d+(?:\.\d+)?)\s*%", text)
    if percent:
        return "percent", float(percent.group(1))
    rank = re.search(rf"{label}.{{0,10}}前\s*(\d+)\s*名", text)
    if rank:
        return "rank", float(rank.group(1))
    return None


# 從公告文字擷取明確戶籍限制。
def _extract_region(text: str) -> str | None:
    for region in TAIWAN_REGIONS:
        escaped = re.escape(region)
        patterns = (
            rf"(?:限|須|需|必須).{{0,10}}(?:設籍|戶籍).{{0,10}}{escaped}",
            rf"(?:設籍|戶籍).{{0,10}}{escaped}.{{0,10}}(?:者|學生|居民)",
        )
        if any(re.search(pattern, text) for pattern in patterns):
            return region
    return None


# 判斷公告是否將資格條件交由附件說明。
def _requires_attachment(text: str) -> bool:
    subject = r"(?:申請資格|詳細資格|資格條件|申請條件|申請對象)"
    reference = r"(?:詳見|請參閱|如|依).{0,6}(?:附件|附檔)"
    return bool(re.search(rf"{subject}.{{0,20}}{reference}", text))


# 判斷公告是否適用一般大專在校生。
def _is_general_college_notice(text: str) -> bool:
    terms = ("大專院校學生", "大專校院學生", "大專在校生", "大學生", "在校學生")
    return any(term in text for term in terms)


# 判斷文字是否表達優先而非必要資格。
def _contains_preference(text: str) -> bool:
    return any(marker in text for marker in PREFERENCE_WORDS)


# 判斷排名資料是否完整。
def _has_rank(profile: StudentProfile) -> bool:
    return profile.class_rank > 0 and profile.class_size > 0


# 比較臺／台異體字後的戶籍地。
def _same_region(required: str, residence: str) -> bool:
    return required.replace("臺", "台") in residence.replace("臺", "台")


# 依標點切分句子，降低跨句關鍵字誤判。
def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。；;\n]", text) if item.strip()]
