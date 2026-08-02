# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
PROFILE_PATH = BASE_DIR / "profile.json"

load_dotenv(ENV_PATH)


def _env_int(name: str, default: int) -> int:
    """將可省略的整數環境變數轉成整數。"""
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"環境變數 {name} 必須是整數") from error


def _env_bool(name: str, default: bool) -> bool:
    """解析明確的布林環境變數，拒絕模糊值。"""
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"環境變數 {name} 必須是 true/false、1/0、yes/no 或 on/off"
    )


LINE_API_URL = "https://api.line.me/v2/bot/message/push"
LHU_SCHOLARSHIP_URL = "https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw"
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
NOTIFY_REVIEW_ITEMS = _env_bool("NOTIFY_REVIEW_ITEMS", False)
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "ScholarshipAgent/3.2 (+https://www.lhu.edu.tw/)"
SOURCE_MAX_PAGES = _env_int("SOURCE_MAX_PAGES", 200)
_LEGACY_SOURCE_FETCH_WORKERS = _env_int("SOURCE_FETCH_WORKERS", 4)
TUN_FETCH_WORKERS = _env_int(
    "TUN_FETCH_WORKERS",
    _LEGACY_SOURCE_FETCH_WORKERS,
)
SOURCE_FETCH_WORKERS = TUN_FETCH_WORKERS
MAX_ATTACHMENT_COUNT = 3
ATTACHMENT_SCOPE_MAX_DEPTH = 5
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
ELIGIBILITY_RULE_VERSION = "eligibility-v13"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_MAX_CALLS_PER_RUN = _env_int("GEMINI_MAX_CALLS_PER_RUN", 50)
GEMINI_MAX_INPUT_TOKENS_PER_RUN = _env_int(
    "GEMINI_MAX_INPUT_TOKENS_PER_RUN",
    600000,
)
GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT = _env_int(
    "GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT",
    12000,
)
GEMINI_MAX_OUTPUT_TOKENS = _env_int("GEMINI_MAX_OUTPUT_TOKENS", 1200)
GEMINI_MAX_PAGES_PER_DOCUMENT = _env_int("GEMINI_MAX_PAGES_PER_DOCUMENT", 2)
GEMINI_MAX_ATTEMPTS = _env_int("GEMINI_MAX_ATTEMPTS", 3)
GEMINI_RETRY_BASE_SECONDS = _env_int("GEMINI_RETRY_BASE_SECONDS", 1)
GEMINI_PROMPT_VERSION = f"eligibility-v2-pages-{GEMINI_MAX_PAGES_PER_DOCUMENT}"
SCHOLARSHIP_FILTER_KEYWORDS = (
    "獎學金",
    "助學金",
    "獎助學金",
    "獎助金",
    "助學計畫",
    "就學貸款",
    "補助",
)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "",
).strip()
LINE_USER_ID = os.getenv("LINE_USER_ID", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


def validate_settings() -> None:
    """驗證 LINE 推播必要的環境變數是否完整。"""
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


def validate_gemini_settings() -> None:
    """驗證明確啟用 Gemini 時所需的 API、模型與預算設定。"""
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
        ("GEMINI_MAX_ATTEMPTS", GEMINI_MAX_ATTEMPTS),
        ("GEMINI_RETRY_BASE_SECONDS", GEMINI_RETRY_BASE_SECONDS),
        ("SOURCE_MAX_PAGES", SOURCE_MAX_PAGES),
        ("TUN_FETCH_WORKERS", TUN_FETCH_WORKERS),
    )
    invalid = [name for name, value in budgets if value < 1]
    if invalid:
        raise RuntimeError(f"Gemini 與來源上限設定必須大於 0：{', '.join(invalid)}")
    if GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT > GEMINI_MAX_INPUT_TOKENS_PER_RUN:
        raise RuntimeError("單份 Gemini input token 上限不得高於單次執行上限")
