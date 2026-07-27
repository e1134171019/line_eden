# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
PROFILE_PATH = BASE_DIR / "profile.json"

load_dotenv(ENV_PATH)


# 將可省略的整數環境變數轉成正整數，格式錯誤時提供欄位名稱。
def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"環境變數 {name} 必須是整數") from error


LINE_API_URL = "https://api.line.me/v2/bot/message/push"
LHU_SCHOLARSHIP_URL = "https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw"
MOE_OVERSEAS_SCHOLARSHIP_URL = "https://www.scholarship.moe.gov.tw/scholarship"
MOE_EU_SCHOLARSHIP_URL = "https://www.scholarship.moe.gov.tw/eu/index/index"
MOE_TOP100_SCHOLARSHIP_URL = "https://www.scholarship.moe.gov.tw/top100/index/index"
CIP_SCHOLARSHIP_URL = "https://cipgrant.fju.edu.tw/news"
OFFICIAL_SOURCE_COUNT = 5
SCHOLARSHIP_DB_FILENAME = "scholarships.db"
GEMINI_CACHE_DB_FILENAME = "gemini_cache.db"
AUTOMATION_LOCK_FILENAME = "scholarship-agent.lock"
AUTOMATION_STATUS_FILENAME = "last_run.json"
AUTOMATION_LOG_DIRNAME = "logs"
AUTOMATION_STALE_LOCK_HOURS = 6
CLOUD_STATE_ARTIFACT_NAME = "scholarship-agent-state"
CLOUD_STATE_ENCRYPTED_FILENAME = "scholarship-state.tar.gz.gpg"
GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
LINE_SUMMARY_BATCH_SIZE = 5
NOTIFY_REVIEW_ITEMS = False
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "ScholarshipAgent/4.0 (+https://github.com/e1134171019/line_eden)"
MAX_ATTACHMENT_COUNT = 3
ATTACHMENT_SCOPE_MAX_DEPTH = 5
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
ATTACHMENT_TEXT_MARKER = "【附件內容】"
UNRESOLVED_ATTACHMENT_MARKER = "【附件未解析】"
GEMINI_PARTIAL_EXCLUSION_MARKER = "【Gemini部分硬性排除】"
ELIGIBILITY_RULE_VERSION = "eligibility-v4"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_MAX_CALLS_PER_RUN = _env_int("GEMINI_MAX_CALLS_PER_RUN", 3)
GEMINI_MAX_INPUT_TOKENS_PER_RUN = _env_int("GEMINI_MAX_INPUT_TOKENS_PER_RUN", 12000)
GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT = _env_int(
    "GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT",
    5000,
)
GEMINI_MAX_OUTPUT_TOKENS = _env_int("GEMINI_MAX_OUTPUT_TOKENS", 1200)
GEMINI_MAX_PAGES_PER_DOCUMENT = _env_int("GEMINI_MAX_PAGES_PER_DOCUMENT", 2)
GEMINI_PROMPT_VERSION = f"eligibility-v2-pages-{GEMINI_MAX_PAGES_PER_DOCUMENT}"
SCHOLARSHIP_FILTER_KEYWORDS = (
    "獎學金",
    "助學金",
    "就學貸款",
    "補助",
)

REQUEST_TIMEOUT_SECONDS = HTTP_TIMEOUT_SECONDS
TEST_MESSAGE = "Eden 獎學金助手：LINE Messaging API 測試成功。"

LINE_CHANNEL_ACCESS_TOKEN = os.getenv(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "",
).strip()
LINE_USER_ID = os.getenv("LINE_USER_ID", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


# 驗證 LINE 推播必要的環境變數是否完整。
def validate_settings() -> None:
    missing_names = [
        name
        for name, value in (
            ("LINE_CHANNEL_ACCESS_TOKEN", LINE_CHANNEL_ACCESS_TOKEN),
            ("LINE_USER_ID", LINE_USER_ID),
        )
        if not value
    ]
    if missing_names:
        joined_names = ", ".join(missing_names)
        raise RuntimeError(f"缺少環境變數：{joined_names}")


# 驗證明確啟用 Gemini 時所需的 API、模型與預算設定。
def validate_gemini_settings() -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("缺少環境變數：GEMINI_API_KEY")
    if not GEMINI_MODEL:
        raise RuntimeError("GEMINI_MODEL 不得為空白")
    budgets = (
        ("GEMINI_MAX_CALLS_PER_RUN", GEMINI_MAX_CALLS_PER_RUN),
        ("GEMINI_MAX_INPUT_TOKENS_PER_RUN", GEMINI_MAX_INPUT_TOKENS_PER_RUN),
        ("GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT", GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT),
        ("GEMINI_MAX_OUTPUT_TOKENS", GEMINI_MAX_OUTPUT_TOKENS),
        ("GEMINI_MAX_PAGES_PER_DOCUMENT", GEMINI_MAX_PAGES_PER_DOCUMENT),
    )
    invalid = [name for name, value in budgets if value < 1]
    if invalid:
        raise RuntimeError(f"Gemini 預算設定必須大於 0：{', '.join(invalid)}")
    if GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT > GEMINI_MAX_INPUT_TOKENS_PER_RUN:
        raise RuntimeError("單份 Gemini input token 上限不得高於單次執行上限")
