# -*- coding: utf-8 -*-

import re

from src.profiles.student_profile import StudentProfile

_PREFERENCE_MARKERS = ("優先", "優先考量", "加分", "酌予優先", "非必要")
_REQUIREMENT_MARKERS = (
    "申請資格",
    "申請對象",
    "須",
    "需",
    "必須",
    "限",
    "僅限",
    "具備",
    "具有",
    "不得",
)
_ACADEMIC_YEAR_MARKERS = (
    "前一學年",
    "上一學年",
    "最近一學年",
    "學年度平均",
    "學年平均",
    "114學年度",
)
_CUMULATIVE_MARKERS = ("歷年平均", "歷年學業", "累積平均", "總平均")
_SCORE_LABELS = ("學業平均", "平均成績", "學業成績")
_CONDUCT_LABELS = ("操行成績", "操行")
_NO_FAILED_MARKERS = (
    "無不及格科目",
    "不得有不及格科目",
    "不得有任何科目不及格",
    "各科均及格",
)
_NO_DISCIPLINE_MARKERS = (
    "未受記過",
    "無記過紀錄",
    "不得有記過",
    "無重大懲處",
    "未受重大懲處",
)
_DUPLICATE_AWARD_MARKERS = (
    "不得重複領取",
    "不得同時領取",
    "未領取其他同性質獎學金",
    "未領取同性質獎學金",
)
_RECOMMENDATION_MARKERS = (
    "須由學校推薦",
    "須經學校推薦",
    "由學校推薦",
    "導師推薦",
    "系主任推薦",
)


# 檢查新個人事實欄位造成的硬性不符合。
def find_extended_exclusions(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    for sentence in _requirement_sentences(text):
        reasons.extend(_nationality_exclusions(sentence, profile))
        reasons.extend(_enrollment_exclusions(sentence, profile))
        reasons.extend(_credit_exclusions(sentence, profile))
        reasons.extend(_residence_exclusions(sentence, profile))
        reasons.extend(_academic_period_exclusions(sentence, profile))
        reasons.extend(_record_exclusions(sentence, profile))
        reasons.extend(_income_exclusions(sentence, profile))
        reasons.extend(_duplicate_award_exclusions(sentence, profile))
        reasons.extend(_recommendation_exclusions(sentence, profile))
    return list(dict.fromkeys(reasons))


# 缺少必要個資時維持 review，不把未知當成不符合。
def find_extended_unknowns(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    for sentence in _requirement_sentences(text):
        reasons.extend(_nationality_unknowns(sentence, profile))
        reasons.extend(_enrollment_unknowns(sentence, profile))
        reasons.extend(_credit_unknowns(sentence, profile))
        reasons.extend(_residence_unknowns(sentence, profile))
        reasons.extend(_academic_period_unknowns(sentence, profile))
        reasons.extend(_record_unknowns(sentence, profile))
        reasons.extend(_income_unknowns(sentence, profile))
        reasons.extend(_duplicate_award_unknowns(sentence, profile))
        reasons.extend(_recommendation_unknowns(sentence, profile))
    return list(dict.fromkeys(reasons))


# 已確認符合的新條件可作為輔助證據，但不能單獨證明適用對象。
def find_extended_matches(text: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    for sentence in _requirement_sentences(text):
        if _requires_taiwan_nationality(sentence) and _is_taiwan_national(profile):
            reasons.append("中華民國國籍符合公告要求。")
        if _requires_enrollment(sentence) and _is_enrolled(profile):
            reasons.append("在學且未休學，符合公告要求。")
        credit = _extract_credit_requirement(sentence)
        if credit is not None and profile.credits_earned >= credit:
            reasons.append(f"累積通過學分符合至少 {credit} 學分門檻。")
        reasons.extend(_residence_matches(sentence, profile))
        reasons.extend(_academic_period_matches(sentence, profile))
        reasons.extend(_record_matches(sentence, profile))
        reasons.extend(_income_matches(sentence, profile))
        reasons.extend(_duplicate_award_matches(sentence, profile))
        reasons.extend(_recommendation_matches(sentence, profile))
    return list(dict.fromkeys(reasons))


# 只處理必要資格句，優先條件不得轉成硬性限制。
def _requirement_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in re.split(r"[。；;\n]", text)
        if sentence.strip()
        and not any(marker in sentence for marker in _PREFERENCE_MARKERS)
        and any(marker in sentence for marker in _REQUIREMENT_MARKERS)
    ]


# 國籍限制只在必要語境中生效。
def _requires_taiwan_nationality(sentence: str) -> bool:
    return any(term in sentence for term in ("中華民國國籍", "本國國籍", "本國籍"))


def _is_taiwan_national(profile: StudentProfile) -> bool:
    value = profile.nationality.replace("臺", "台")
    return any(term in value for term in ("中華民國", "台灣", "本國"))


def _nationality_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    if not _requires_taiwan_nationality(sentence) or not profile.nationality:
        return []
    if _is_taiwan_national(profile):
        return []
    return ["公告要求中華民國國籍，與目前國籍不符。"]


def _nationality_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_taiwan_nationality(sentence) and not profile.nationality:
        return ["公告有國籍限制，但 profile.json 未填國籍。"]
    return []


# 在學限制明確要求目前仍具學籍且未休學。
def _requires_enrollment(sentence: str) -> bool:
    return "在學" in sentence or "未休學" in sentence


def _is_enrolled(profile: StudentProfile) -> bool:
    return "在學" in profile.enrollment_status and "休學" not in profile.enrollment_status


def _enrollment_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    if not _requires_enrollment(sentence) or not profile.enrollment_status:
        return []
    if _is_enrolled(profile):
        return []
    return ["公告要求在學且未休學，與目前學籍狀態不符。"]


def _enrollment_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_enrollment(sentence) and not profile.enrollment_status:
        return ["公告要求在學狀態，但 profile.json 未填學籍狀態。"]
    return []


# 擷取至少修滿或取得的學分門檻。
def _extract_credit_requirement(sentence: str) -> int | None:
    patterns = (
        r"(?:至少|須|需|必須).{0,10}?(\d{1,3})\s*學分",
        r"(?:已修|累計|修滿|取得).{0,10}?(\d{1,3})\s*學分.{0,8}?(?:以上|至少)",
    )
    for pattern in patterns:
        match = re.search(pattern, sentence)
        if match:
            return int(match.group(1))
    return None


def _credit_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    required = _extract_credit_requirement(sentence)
    if required is None or profile.credits_earned <= 0:
        return []
    if profile.credits_earned >= required:
        return []
    return [f"累積通過學分 {profile.credits_earned} 未達 {required} 學分門檻。"]


def _credit_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    if _extract_credit_requirement(sentence) is not None and profile.credits_earned <= 0:
        return ["公告有學分門檻，但 profile.json 未填累積通過學分。"]
    return []


# 擷取區鄉鎮與設籍年限，縣市條件仍由既有規則處理。
def _extract_residence_district(sentence: str) -> str | None:
    anchor = re.search(r"(?:設籍|戶籍)", sentence)
    if anchor is None:
        return None
    tail = sentence[anchor.end() : anchor.end() + 30]
    match = re.search(
        r"((?:[\u4e00-\u9fff]{2,3}市)?[\u4e00-\u9fff]{1,4}(?:區|鄉|鎮))",
        tail,
    )
    return match.group(1) if match else None


def _extract_residence_years(sentence: str) -> float | None:
    match = re.search(
        r"(?:設籍|戶籍).{0,24}?滿\s*(\d+(?:\.\d+)?)\s*(年|個月|月)",
        sentence,
    )
    if match is None:
        return None
    value = float(match.group(1))
    return value if match.group(2) == "年" else value / 12


def _same_residence(required: str, residence: str) -> bool:
    normalized_required = required.replace("臺", "台").replace(" ", "")
    normalized_residence = residence.replace("臺", "台").replace(" ", "")
    return normalized_required in normalized_residence


def _residence_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    district = _extract_residence_district(sentence)
    if district and profile.residence and not _same_residence(district, profile.residence):
        reasons.append(f"公告限設籍於 {district}，與目前戶籍地不符。")
    years = _extract_residence_years(sentence)
    if years is not None and profile.residence_years > 0 and profile.residence_years < years:
        reasons.append(
            f"設籍年數約 {profile.residence_years:g} 年，未達 {years:g} 年門檻。"
        )
    return reasons


def _residence_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if _extract_residence_district(sentence) and not profile.residence:
        reasons.append("公告有限定行政區戶籍，但 profile.json 未填完整戶籍地。")
    if _extract_residence_years(sentence) is not None and profile.residence_years <= 0:
        reasons.append("公告有限定設籍年數，但 profile.json 未填設籍年數。")
    return reasons


def _residence_matches(sentence: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    district = _extract_residence_district(sentence)
    if district and profile.residence and _same_residence(district, profile.residence):
        reasons.append(f"戶籍地符合 {district} 限制。")
    years = _extract_residence_years(sentence)
    if years is not None and profile.residence_years >= years:
        reasons.append(f"設籍年數符合至少 {years:g} 年門檻。")
    return reasons


# 只補足前一學年與累積平均；一般或前一學期門檻沿用既有規則。
def _period_average_requirement(sentence: str) -> tuple[str, float] | None:
    threshold = _extract_score(sentence, _SCORE_LABELS)
    if threshold is None:
        return None
    if any(marker in sentence for marker in _ACADEMIC_YEAR_MARKERS):
        return "academic_year", threshold
    if any(marker in sentence for marker in _CUMULATIVE_MARKERS):
        return "cumulative", threshold
    return None


def _extract_score(sentence: str, labels: tuple[str, ...]) -> float | None:
    label = "|".join(re.escape(item) for item in labels)
    score = r"(\d{1,3}(?:\.\d+)?)"
    patterns = (
        rf"(?:{label}).{{0,16}}?{score}\s*分?\s*(?:以上|或以上)",
        rf"(?:{label}).{{0,16}}?(?:不得低於|至少|須達|需達|達){score}\s*分?",
    )
    for pattern in patterns:
        match = re.search(pattern, sentence)
        if match:
            return float(match.group(1))
    return None


def _period_average(profile: StudentProfile, period: str) -> float:
    if period == "academic_year":
        return profile.academic_year_average
    return profile.cumulative_average


def _period_label(period: str) -> str:
    return "前一學年平均" if period == "academic_year" else "累積平均"


def _academic_period_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    requirement = _period_average_requirement(sentence)
    if requirement is None:
        return []
    period, threshold = requirement
    actual = _period_average(profile, period)
    if actual <= 0 or actual >= threshold:
        return []
    return [f"{_period_label(period)} {actual:g} 未達 {threshold:g} 分門檻。"]


def _academic_period_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    requirement = _period_average_requirement(sentence)
    if requirement is None:
        return []
    period, _ = requirement
    if _period_average(profile, period) <= 0:
        return [f"公告有{_period_label(period)}門檻，但 profile.json 未填該成績。"]
    if "每學期" in sentence and _extract_score(sentence, _CONDUCT_LABELS) is not None:
        return ["公告要求每學期操行成績，但 profile.json 只有最近一學期操行。"]
    return []


def _academic_period_matches(sentence: str, profile: StudentProfile) -> list[str]:
    requirement = _period_average_requirement(sentence)
    if requirement is None:
        return []
    period, threshold = requirement
    actual = _period_average(profile, period)
    if actual > 0 and actual >= threshold:
        return [f"{_period_label(period)}符合 {threshold:g} 分門檻。"]
    return []


# 不及格與懲處條件都採 true／false／unknown 三態。
def _record_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if any(marker in sentence for marker in _NO_FAILED_MARKERS) and profile.has_failed_courses:
        reasons.append("公告要求無不及格科目，但目前紀錄有不及格科目。")
    if any(marker in sentence for marker in _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline:
        reasons.append("公告要求無記過或重大懲處，但目前紀錄不符。")
    return reasons


def _record_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if any(marker in sentence for marker in _NO_FAILED_MARKERS) and profile.has_failed_courses is None:
        reasons.append("公告要求無不及格科目，但 profile.json 尚未確認。")
    if any(marker in sentence for marker in _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline is None:
        reasons.append("公告要求無記過或重大懲處，但 profile.json 尚未確認。")
    return reasons


def _record_matches(sentence: str, profile: StudentProfile) -> list[str]:
    reasons: list[str] = []
    if any(marker in sentence for marker in _NO_FAILED_MARKERS) and profile.has_failed_courses is False:
        reasons.append("無不及格科目，符合公告要求。")
    if any(marker in sentence for marker in _NO_DISCIPLINE_MARKERS) and profile.has_major_discipline is False:
        reasons.append("無記過或重大懲處，符合公告要求。")
    return reasons


# 家庭所得未提供時只標待確認。
def _extract_income_limit(sentence: str) -> float | None:
    match = re.search(
        r"家庭(?:年)?(?:總)?所得.{0,20}?(?:未超過|不得超過|低於|不超過)"
        r"\s*([\d,]+(?:\.\d+)?)\s*(萬)?元",
        sentence,
    )
    if match is None:
        return None
    value = float(match.group(1).replace(",", ""))
    return value * 10000 if match.group(2) else value


def _income_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    limit = _extract_income_limit(sentence)
    if limit is None or profile.household_income is None:
        return []
    if profile.household_income <= limit:
        return []
    return [f"家庭年所得超過公告上限 {limit:g} 元。"]


def _income_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    if _extract_income_limit(sentence) is not None and profile.household_income is None:
        return ["公告有家庭所得限制，但 profile.json 未填家庭年所得。"]
    return []


def _income_matches(sentence: str, profile: StudentProfile) -> list[str]:
    limit = _extract_income_limit(sentence)
    if limit is not None and profile.household_income is not None:
        if profile.household_income <= limit:
            return ["家庭年所得符合公告上限。"]
    return []


# 是否已領同性質獎學金採三態，不知道時不得排除。
def _requires_no_duplicate_award(sentence: str) -> bool:
    return any(marker in sentence for marker in _DUPLICATE_AWARD_MARKERS)


def _duplicate_award_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_no_duplicate_award(sentence) and profile.has_received_similar_scholarship:
        return ["公告禁止重複領取同性質獎學金，目前紀錄不符。"]
    return []


def _duplicate_award_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_no_duplicate_award(sentence):
        if profile.has_received_similar_scholarship is None:
            return ["公告禁止重複領取，但 profile.json 尚未確認領獎狀態。"]
    return []


def _duplicate_award_matches(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_no_duplicate_award(sentence):
        if profile.has_received_similar_scholarship is False:
            return ["未領取同性質獎學金，符合公告要求。"]
    return []


# 推薦屬必要程序；尚未確認時列待辦，明確無法取得才排除。
def _requires_recommendation(sentence: str) -> bool:
    return any(marker in sentence for marker in _RECOMMENDATION_MARKERS)


def _recommendation_exclusions(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_recommendation(sentence) and profile.can_obtain_recommendation is False:
        return ["公告要求學校、導師或系主任推薦，但目前確認無法取得。"]
    return []


def _recommendation_unknowns(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_recommendation(sentence) and profile.can_obtain_recommendation is None:
        return ["公告需要推薦，須向學校、導師或系主任確認。"]
    return []


def _recommendation_matches(sentence: str, profile: StudentProfile) -> list[str]:
    if _requires_recommendation(sentence) and profile.can_obtain_recommendation:
        return ["已確認可取得公告要求的推薦。"]
    return []
