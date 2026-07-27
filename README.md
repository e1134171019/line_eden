# Scholarship Agent

目前包含兩個階段：  
第一階段驗證 LINE Messaging API 推播。  
第二階段加入龍華獎學金公告蒐集、SQLite 去重與 dry-run。

## 專案結構

```text
scholarship-agent/
├── AGENTS.md
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── config.py
├── main.py
├── src/
│   ├── AGENTS.md
│   ├── __init__.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base_collector.py
│   │   └── lhu_collector.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── scholarship.py
│   └── notifiers/
│       ├── __init__.py
│       └── line_notifier.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── scholarship_repository.py
│   └── services/
│       ├── __init__.py
│       └── scholarship_service.py
├── tests/
│   ├── AGENTS.md
│   ├── fixtures/
│   │   └── lhu_scholarships.html
│   ├── output/
│   ├── test_lhu_collector.py
│   ├── test_line_notifier.py
│   ├── test_scholarship_repository.py
│   └── test_scholarship_service.py
├── data/
├── docs/
│   ├── coding.md
│   └── git.md
├── logs/
└── temp/
```

## Windows PowerShell 安裝

```powershell
cd scholarship-agent
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

若 PowerShell 阻擋虛擬環境啟用，可在目前視窗暫時執行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
./.venv/Scripts/Activate.ps1
```

## 建立環境變數

```powershell
Copy-Item .env.example .env
notepad .env
```

將 `.env` 改成：

```dotenv
LINE_CHANNEL_ACCESS_TOKEN=你的完整ChannelAccessToken
LINE_USER_ID=你的U開頭UserID
```

不要將 `.env` 上傳到 GitHub。

## 環境確認

```powershell
python --version
pip --version
pytest --version
```

## 執行測試

```powershell
python -m pytest tests/
```

測試使用模擬回應，不會真的傳送 LINE 訊息。

## 第二階段：dry-run（不傳 LINE）

```powershell
python main.py --dry-run
```

輸出會包含：

- 本次抓到的公告
- 判定為新公告的資料
- dry-run 狀態說明

## 第二階段：正式模式（會傳 LINE）

```powershell
python main.py
```

正式模式規則：

- 只通知第一次出現的新公告
- 成功傳送後才標記已通知
- 首次執行若抓到大量歷史公告，會改為單則摘要通知避免洗版

## 正式模式上線前檢查清單

- 環境變數：確認 `.env` 內 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_USER_ID` 指向測試帳號後，再切換正式帳號。
- 資料庫備份：正式上線前先備份 `data/scholarships.db`，避免既有通知狀態遺失。
- 訊息頻率：先用 `python main.py --dry-run` 觀察新公告數量與內容，確認不會短時間大量推播。

## 第三階段前的噪音控制

- 已加入公告關鍵字過濾（預設：獎學金、助學金、就學貸款、補助）。
- 已加入 `category` 分類欄位（`scholarship`、`loan`、`subsidy`、`other`）。
- 如需調整訊息精準度，可修改 `config.py` 的 `SCHOLARSHIP_FILTER_KEYWORDS`。

## 傳送第一則測試訊息

```powershell
python -c "from config import LINE_API_URL, LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, REQUEST_TIMEOUT_SECONDS, TEST_MESSAGE, validate_settings; from src.notifiers.line_notifier import send_text_message; validate_settings(); send_text_message(LINE_API_URL, LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, TEST_MESSAGE, REQUEST_TIMEOUT_SECONDS)"
```

成功時終端機會顯示：

```text
命令結束且未拋出錯誤，即代表測試訊息送出成功。
```
