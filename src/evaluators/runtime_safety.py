# -*- coding: utf-8 -*-

from datetime import date, datetime
import re

from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

DEADLINE_CONTEXT = (
    "截止",
    "期限",
    "申請期間",
    "受理期間",
    "前交",
    "前完成",
    "前自行",
    "前寄",
    "前送",
    "止",
    "逾期",
    "郵戳",
)
FULL_TIME_TERMS = ("全職學生", "全時學生", "全日制學生")


# 依公告日期推定未標年份的申請截止日，並只接受具截止語境的日期。
def extract_application_deadline(text: str, published_date: str) -> date | None:
    published = _parse_iso_date(published_date)
    candidates = [
        parsed
        for parsed in (_parse_deadline_match(match, published) for match in _date_matches(text))
        if parsed is not None
    ]
    return max(candidates) if candidates else None


# 申請期限已過時直接排除，避免歷史公告再次進入推播候選。
def find_deadline_exclusions(
    scholarship: Scholarship,
    text: str,
    today: date | None = None,
) -> list[str]:
    deadline = extract_application_deadline(text, scholarship.published_date)
    current = today or date.today()
    if deadline is not None and deadline < current:
        return [f"申請截止日 {deadline.isoformat()} 已過，不推播。"]
    return []


# 全職學生限制與進修或在職背景存在歧義時維持 review。
def find_runtime_unknowns(text: str, profile: StudentProfile) -> list[str]:
    if not _requires_full_time_student(text):
        return []
    if "進修" in profile.program_type or profile.employed:
        return ["公告要求全職學生，與進修／在職背景的適用性需人工確認。"]
    return []


# 找出公告中所有可能日期，保留前後文字供截止語境判斷。
def _date_matches(text: str) -> list[re.Match[str]]:
    pattern = re.compile(
        r"(?:(?P<roc>\d{3})年|(?P<year>20\d{2})[年\-/.])?"
        r"(?P<month>\d{1,2})(?:月|[\-/.])(?P<day>\d{1,2})日?"
    )
    return list(pattern.finditer(text))


# 將單一日期候選轉成西元日期；沒有截止語境時忽略。
def _parse_deadline_match(match: re.Match[str], published: date | None) -> date | None:
    context = match.string[max(0, match.start() - 18):min(len(match.string), match.end() + 18)]
    if not any(marker in context for marker in DEADLINE_CONTEXT):
        return None
    year = _match_year(match, published)
    try:
        return date(year, int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


# ROC 年轉西元；未標年份時使用公告發布年份。
def _match_year(match: re.Match[str], published: date | None) -> int:
    if match.group("roc"):
        return int(match.group("roc")) + 1911
    if match.group("year"):
        return int(match.group("year"))
    return published.year if published else date.today().year


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
