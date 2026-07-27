# Scholarship Agent

目前包含兩個階段：  
第一階段驗證 LINE Messaging API 推播。  
第二階段加入龍華獎學金公告蒐集、SQLite 狀態管理、歷史基準與 dry-run。

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
│   ├── notifiers/
│   │   ├── __init__.py
│   │   └── line_notifier.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── scholarship_repository.py
│   └── services/
│       ├── __init__.py
│       └── scholarship_service.py
├── tests/
│   ├── AGENTS.md
│   ├── fixtures/
│   ├── output/
│   ├── test_lhu_collector.py
│   ├── test_line_notifier.py
│   ├── test_main.py
│   ├── test_scholarship_repository.py
│   └── test_scholarship_service.py
├── data/
├── docs/
├── logs/
└── temp/
```

## Windows PowerShell 安裝

```powershell
cd C:/scholarship-agent
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "./.venv/Scripts/Activate.ps1"
python -m pip install -r requirements.txt
```

## 建立環境變數

```powershell
Copy-Item .env.example .env
code .env
```

將 `.env` 改成：

```dotenv
LINE_CHANNEL_ACCESS_TOKEN=你的完整ChannelAccessToken
LINE_USER_ID=你的U開頭UserID
```

不要將 `.env` 上傳到 GitHub。

## 執行測試

```powershell
python -m pytest tests/
```

測試使用暫存資料庫與模擬 LINE 回應，不會傳送真實訊息，也不會修改 `data/` 正式資料庫。

## Dry-run：檢查待通知公告

```powershell
python main.py --dry-run
```

行為：

- 蒐集並保存 `discovered` 公告。
- 顯示目前 `pending` 公告。
- 不修改 `baseline_at`。
- 不修改 `notified_at`。
- 不驗證 LINE Token。
- 不傳送 LINE。

重複執行 dry-run 時，尚未建立基準或成功通知的公告仍會保持 pending。

## 首次上線：建立歷史基準

只在首次正式上線時執行一次：

```powershell
python main.py --initialize-baseline
```

行為：

- 蒐集目前網站已有公告。
- 將尚未通知的現有公告寫入 `baseline_at`。
- 不修改 `notified_at`。
- 不驗證 LINE Token。
- 不傳送 LINE。

建立基準後再檢查：

```powershell
python main.py --dry-run
```

正常情況下，既有歷史公告不再列為 pending。未來網站新增的公告才會成為待通知資料。

`--dry-run` 與 `--initialize-baseline` 為互斥模式，不能同時使用。

## 正式模式：傳送待通知公告

```powershell
python main.py
```

正式模式規則：

- 驗證 `.env` 中的 LINE 設定。
- 只推播 `baseline_at IS NULL` 且 `notified_at IS NULL` 的公告。
- LINE 成功送出後才寫入 `notified_at`。
- LINE 發送失敗時保留 pending，供下次重試。

正式執行前應先完成歷史基準，避免將所有舊公告當成待通知資料。

## 上線前檢查

```powershell
python -m pytest tests/
python main.py --dry-run
git status
```

確認：

- 測試全部通過。
- `.env` 未被 Git 追蹤。
- dry-run 的標題、日期與網址正確。
- pending 數量符合預期。

## 公告篩選

目前使用 `config.py` 的 `SCHOLARSHIP_FILTER_KEYWORDS` 過濾公告，預設包含：

- 獎學金
- 助學金
- 就學貸款
- 補助

公告分類欄位目前包含 `scholarship`、`loan`、`subsidy` 與 `other`。
