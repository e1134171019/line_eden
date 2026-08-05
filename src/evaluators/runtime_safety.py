# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import date, datetime
import re

from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

APPLICATION_ACTION_MARKERS = (
    "申請",
    "申辦",
    "報名",
    "受理",
    "收件",
    "繳交",
    "交至",
    "寄至",
    "寄送",
    "送件",
    "上傳",
    "登錄",
    "完成",
    "填寫",
)
DEADLINE_MARKERS = (
    "截止",
    "期限",
    "期間",
    "前",
    "至",
    "止",
    "逾期",
    "郵戳",
)
DIRECT_APPLICANT_MARKERS = (
    "請於",
    "申請期間",
    "申請時間",
    "申請期限",
    "申請截止",
    "報名期間",
    "報名時間",
    "報名截止",
    "受理期間",
    "收件期間",
    "收件截止",
    "受理截止",
    "完成申請",
    "完成網路報名",
    "線上申請",
    "系統申請",
    "系統報名",
    "上網登錄",
    "自行寄",
    "交至",
    "寄至",
    "上傳",
)
NON_APPLICATION_TIME_MARKERS = (
    "職涯輔導時間",
    "輔導時間",
    "活動時間",
    "活動期間",
    "執行期間",
    "服務期間",
    "課程日期",
    "課程時間",
    "上課時間",
)
ADMINISTRATIVE_MARKERS = (
    "校方覆核",
    "學校覆核",
    "函送",
    "彙送",
    "審查期限",
    "核定日期",
)
FULL_TIME_TERMS = ("全職學生", "全時學生", "全日制學生")
EVERGREEN_MARKERS = (
    "全年受理",
    "常年受理",
    "全年皆可申請",
    "隨時申請",
    "隨到隨審",
    "長期受理",
    "無申請期限",
)
STALE_UNKNOWN_DAYS = 180
DATE_PATTERN = re.compile(
    r"(?:(?P<year_value>20\d{2}|\d{3})(?:年|[\-/.]))?"
    r"(?P<month>\d{1,2})(?:月|[\-/.])(?P<day>\d{1,2})日?"
)
NAMED_CYCLE_PATTERN = re.compile(
    r"(?<!\d)(?P<year>20\d{2}|1\d{2})\s*(?:學年度|年度)"
)
_DATE_TOKEN = (
    r"(?:(?:20\d{2}|\d{3})(?:年|[\-/.]))?"
    r"\d{1,2}(?:月|[\-/.])\d{1,2}日?"
)
EXPLICIT_DEADLINE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        rf"於\s*{_DATE_TOKEN}\s*前.{{0,16}}(?:登錄|申請|送件|繳交|完成)",
        rf"(?:收件|系統|受理).{{0,8}}(?:截止|開放至).{{0,8}}{_DATE_TOKEN}",
        rf"即日起.{{0,16}}至\s*{_DATE_TOKEN}\s*(?:止|截止)",
        rf"{_DATE_TOKEN}.{{0,12}}郵戳為憑",
    )
)

UPCOMING = "upcoming"
OPEN = "open"
EXPIRED = "expired"
DEADLINE_UNKNOWN = "deadline_unknown"
STALE_UNKNOWN = "stale_unknown"
EVERGREEN = "evergreen"
NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ApplicationPeriod:
    """公告申請期間與相對於檢查日的狀態。"""

    start_date: date | None
    deadline: date | None
    status: str


# 只從學生申請行為語境擷取日期；同一期間取結束日，多個必要步驟取最早期限。
def extract_application_deadline(text: str, published_date: str) -> date | None:
    published = _parse_iso_date(published_date)
    ranked = _explicit_deadlines(text, published)
    for segment in _deadline_segments(text):
        if not _is_application_deadline_segment(segment):
            continue
        candidates = _dates_for_publication_cycle(segment, published)
        if not candidates:
            continue
        priority = 0 if any(marker in segment for marker in DIRECT_APPLICANT_MARKERS) else 1
        ranked.append((priority, max(candidates)))
    ranked = _ranked_for_publication_cycle(ranked, published)
    if not ranked:
        return None
    best_priority = min(priority for priority, _ in ranked)
    return min(deadline for priority, deadline in ranked if priority == best_priority)


# 直接辨識動作前置、收件截止、即日起與郵戳句型。
def _explicit_deadlines(
    text: str,
    published: date | None,
) -> list[tuple[int, date]]:
    ranked: list[tuple[int, date]] = []
    for pattern in EXPLICIT_DEADLINE_PATTERNS:
        for match in pattern.finditer(text):
            candidates = _dates_for_publication_cycle(match.group(0), published)
            if candidates:
                ranked.append((0, max(candidates)))
    return ranked


# 只有明確日期區間才擷取開始日，避免把單一截止日誤當開放日。
def extract_application_start(text: str, published_date: str) -> date | None:
    published = _parse_iso_date(published_date)
    starts: list[date] = []
    for segment in _deadline_segments(text):
        if not _is_application_deadline_segment(segment):
            continue
        candidates = _dates_for_publication_cycle(segment, published)
        if len(candidates) >= 2:
            starts.append(min(candidates))
    return min(starts) if starts else None


# 將申請起訖日轉為 upcoming、open、expired、evergreen 或未知類型。
def classify_application_period(
    text: str,
    published_date: str,
    today: date | None = None,
) -> ApplicationPeriod:
    current = today or date.today()
    start = extract_application_start(text, published_date)
    deadline = extract_application_deadline(text, published_date)
    if deadline is not None and deadline < current:
        return ApplicationPeriod(start, deadline, EXPIRED)
    if start is not None and start > current:
        return ApplicationPeriod(start, deadline, UPCOMING)
    if deadline is not None:
        return ApplicationPeriod(start, deadline, OPEN)
    if _is_historical_named_cycle(text, current):
        return ApplicationPeriod(start, None, STALE_UNKNOWN)
    if any(marker in text for marker in EVERGREEN_MARKERS):
        return ApplicationPeriod(start, None, EVERGREEN)
    if _is_undated_ambiguous(text, published_date, current):
        return ApplicationPeriod(start, None, STALE_UNKNOWN)
    if _is_stale_unknown(text, published_date, current):
        return ApplicationPeriod(start, None, STALE_UNKNOWN)
    return ApplicationPeriod(start, None, DEADLINE_UNKNOWN)


# 明示為舊年度的固定方案頁，即使缺少截止日期也不得視為當期可申請。
def _is_historical_named_cycle(text: str, current: date) -> bool:
    cycle_years = _named_cycle_years(text)
    return bool(cycle_years) and max(cycle_years) < current.year


# 無發布日且沒有當年度標記時，不得把「10/1 至 10/31」猜成今年。
def _is_undated_ambiguous(text: str, published_date: str, current: date) -> bool:
    if _parse_iso_date(published_date) is not None:
        return False
    cycle_years = _named_cycle_years(text)
    return current.year not in cycle_years


def _named_cycle_years(text: str) -> list[int]:
    years: list[int] = []
    for match in NAMED_CYCLE_PATTERN.finditer(text):
        value = int(match.group("year"))
        years.append(value + 1911 if value < 1000 else value)
    return years


# 發布時間已久且正文沒有當年度訊號時，避免當成目前可申請的期限未知公告。
def _is_stale_unknown(text: str, published_date: str, current: date) -> bool:
    published = _parse_iso_date(published_date)
    if published is None or (current - published).days <= STALE_UNKNOWN_DAYS:
        return False
    current_roc_year = current.year - 1911
    year_markers = (
        str(current.year),
        f"{current_roc_year}年",
        f"{current_roc_year}學年度",
    )
    return not any(marker in text for marker in year_markers)


# 申請期限已過時直接排除，避免歷史公告再次進入推播候選。
def find_deadline_exclusions(
    scholarship: Scholarship,
    text: str,
    today: date | None = None,
) -> list[str]:
    period = classify_application_period(text, scholarship.published_date, today)
    if period.status == EXPIRED and period.deadline is not None:
        return [f"申請截止日 {period.deadline.isoformat()} 已過，不推播。"]
    if period.status == STALE_UNKNOWN:
        return ["公告發布時間已久且無當年度申請證據，列為歷史期限未知。"]
    return []


# 全職學生限制與進修或在職背景存在歧義時維持 review。
def find_runtime_unknowns(text: str, profile: StudentProfile) -> list[str]:
    if not _requires_full_time_student(text):
        return []
    if "進修" in profile.program_type or profile.employed:
        return ["公告要求全職學生，與進修／在職背景的適用性需人工確認。"]
    return []


# 依標點與時間欄位切開文字，避免申請期限和活動日期互相污染。
def _deadline_segments(text: str) -> list[str]:
    label = (
        r"(?=(?:本次)?(?:申請|報名|受理|收件|繳交|職涯輔導|輔導|活動|執行|服務|課程)"
        r"(?:時間|期間|期限|截止|日期))"
    )
    return [
        segment.strip()
        for segment in re.split(rf"[。；;\n]|{label}", text)
        if segment.strip()
    ]


# 只接受申請行為及截止語氣同時存在的片段，排除活動與行政時程。
def _is_application_deadline_segment(segment: str) -> bool:
    if any(marker in segment for marker in NON_APPLICATION_TIME_MARKERS):
        return False
    has_action = any(marker in segment for marker in APPLICATION_ACTION_MARKERS)
    has_deadline = any(marker in segment for marker in DEADLINE_MARKERS)
    if not has_action or not has_deadline:
        return False
    if any(marker in segment for marker in ADMINISTRATIVE_MARKERS):
        return any(marker in segment for marker in DIRECT_APPLICANT_MARKERS)
    return True


def _dates_for_publication_cycle(segment: str, published: date | None) -> list[date]:
    candidates = _parse_segment_dates(segment, published)
    if published is None:
        return candidates
    current_or_future = [candidate for candidate in candidates if candidate.year >= published.year]
    return current_or_future or candidates


def _ranked_for_publication_cycle(
    ranked: list[tuple[int, date]],
    published: date | None,
) -> list[tuple[int, date]]:
    if published is None:
        return ranked
    current_or_future = [item for item in ranked if item[1].year >= published.year]
    return current_or_future or ranked


# 擷取同一申請語意片段中的所有有效日期。
def _parse_segment_dates(segment: str, published: date | None) -> list[date]:
    return [
        parsed
        for parsed in (
            _parse_date_match(match, published)
            for match in DATE_PATTERN.finditer(segment)
        )
        if parsed is not None
    ]


# 將單一日期候選轉成西元日期；民國斜線日期同樣支援。
def _parse_date_match(match: re.Match[str], published: date | None) -> date | None:
    month = int(match.group("month"))
    day = int(match.group("day"))
    year = _match_year(match.group("year_value"), month, published)
    if year is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


# 民國年轉西元；跨年且未標年份時依公告日期推定下一年。
def _match_year(year_value: str | None, month: int, published: date | None) -> int | None:
    if year_value:
        value = int(year_value)
        return value + 1911 if len(year_value) == 3 else value
    if not published:
        return None
    if published.month - month > 6:
        return published.year + 1
    return published.year


# 解析 Scholarship 內標準化後的 YYYY-MM-DD 發布日期。
def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# 判斷全職學生是否位於申請對象或必要資格語境。
def _requires_full_time_student(text: str) -> bool:
    for sentence in re.split(r"[。；;\n]", text):
        if not any(term in sentence for term in FULL_TIME_TERMS):
            continue
        if any(marker in sentence for marker in ("申請對象", "申請資格", "限於", "須為", "必須")):
            return True
    return False
