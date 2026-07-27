# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
PROFILE_PATH = BASE_DIR / "profile.json"

load_dotenv(ENV_PATH)

LINE_API_URL = "https://api.line.me/v2/bot/message/push"
LHU_SCHOLARSHIP_URL = "https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw"
SCHOLARSHIP_DB_FILENAME = "scholarships.db"
GEMINI_CACHE_DB_FILENAME = "gemini_cache.db"
LINE_SUMMARY_BATCH_SIZE = 5
NOTIFY_REVIEW_ITEMS = False
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "ScholarshipAgent/3.2 (+https://www.lhu.edu.tw/)"
MAX_ATTACHMENT_COUNT = 3
ATTACHMENT_SCOPE_MAX_DEPTH = 5
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
ATTACHMENT_TEXT_MARKER = "【附件內容】"
UNRESOLVED_ATTACHMENT_MARKER = "【附件未解析】"
GEMINI_PROMPT_VERSION = "eligibility-v1"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_MAX_CALLS_PER_RUN = int(os.getenv("GEMINI_MAX_CALLS_PER_RUN", "3"))
GEMINI_MAX_INPUT_TOKENS_PER_RUN = int(
    os.getenv("GEMINI_MAX_INPUT_TOKENS_PER_RUN", "12000")
)
GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT = int(
    os.getenv("GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT", "5000")
)
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1200"))
GEMINI_MAX_PAGES_PER_DOCUMENT = int(os.getenv("GEMINI_MAX_PAGES_PER_DOCUMENT", "2"))
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


# 驗證明確啟用 Gemini 時所需的 API 設定。
def validate_gemini_settings() -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("缺少環境變數：GEMINI_API_KEY")
    if GEMINI_MAX_CALLS_PER_RUN < 1:
        raise RuntimeError("GEMINI_MAX_CALLS_PER_RUN 必須大於 0")
    if GEMINI_MAX_PAGES_PER_DOCUMENT < 1:
        raise RuntimeError("GEMINI_MAX_PAGES_PER_DOCUMENT 必須大於 0")
