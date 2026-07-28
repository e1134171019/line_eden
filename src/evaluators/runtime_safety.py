# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import date, datetime
import re

from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

APPLICATION_ACTION_MARKERS = (
    "申請",
    "報名",
    "受理",
    "收件",
    "繳交",
    "交至",
    "寄至",
    "寄送",
    "送件",
    "上傳",
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
    "完成申請",
    "完成網路報名",
    "線上申請",
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
DATE_PATTERN = re.compile(
    r"(?:(?P<year_value>20\d{2}|\d{3})(?:年|[\-/.]))?"
    r"(?P<month>\d{1,2})(?:月|[\-/.])(?P<day>\d{1,2})日?"
)

UPCOMING = "upcoming"
OPEN = "open"
EXPIRED = "expired"
DEADLINE_UNKNOWN = "deadline_unknown"
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
    ranked: list[tuple[int, date]] = []
    for segment in _deadline_segments(text):
        if not _is_application_deadline_segment(segment):
            continue
        candidates = _parse_segment_dates(segment, published)
        if not candidates:
            continue
        priority = 0 if any(marker in segment for marker in DIRECT_APPLICANT_MARKERS) else 1
        ranked.append((priority, max(candidates)))
    if not ranked:
        return None
    best_priority = min(priority for priority, _ in ranked)
    return min(deadline for priority, deadline in ranked if priority == best_priority)


# 只有明確日期區間才擷取開始日，避免把單一截止日誤當開放日。
def extract_application_start(text: str, published_date: str) -> date | None:
    published = _parse_iso_date(published_date)
    starts: list[date] = []
    for segment in _deadline_segments(text):
        if not _is_application_deadline_segment(segment):
            continue
        candidates = _parse_segment_dates(segment, published)
        if len(candidates) >= 2:
            starts.append(min(candidates))
    return min(starts) if starts else None


# 將申請起訖日轉為 upcoming、open、expired 或 deadline_unknown。
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
    return ApplicationPeriod(start, deadline, DEADLINE_UNKNOWN)


# 申請期限已過時直接排除，避免歷史公告再次進入推播候選。
def find_deadline_exclusions(
    scholarship: Scholarship,
    text: str,
    today: date | None = None,
) -> list[str]:
    period = classify_application_period(text, scholarship.published_date, today)
    if period.status == EXPIRED and period.deadline is not None:
        return [f"申請截止日 {period.deadline.isoformat()} 已過，不推播。"]
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
    try:
        return date(year, month, day)
    except ValueError:
        return None


# 民國年轉西元；跨年且未標年份時依公告日期推定下一年。
def _match_year(year_value: str | None, month: int, published: date | None) -> int:
    if year_value:
        value = int(year_value)
        return value + 1911 if len(year_value) == 3 else value
    if not published:
        return date.today().year
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
