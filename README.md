# Scholarship Agent

目前包含三個階段：

1. LINE Messaging API 推播。
2. 龍華獎學金公告蒐集、SQLite 去重、歷史基準與 dry-run。
3. 讀取公告內頁，依本機私密學生背景判斷適合度，只推播明確適合的公告。

## 核心流程

```text
公告列表
→ 公告內頁文字
→ 個人背景資格判斷
→ eligible：可推播
→ review：條件不足，預設不推播
→ ineligible：明確不符，不推播
```

`review` 與 `ineligible` 仍會保存於 SQLite，避免每次重複分析。個人背景改變時，系統會以背景指紋重新評估尚未通知的公告。

## Windows PowerShell 安裝

正式執行環境：

```powershell
cd C:/scholarship-agent
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "./.venv/Scripts/Activate.ps1"
python -m pip install -r requirements.txt
```

開發與測試環境：

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest tests/
```

## LINE 私密設定

```powershell
Copy-Item .env.example .env
code .env
```

`.env`：

```dotenv
LINE_CHANNEL_ACCESS_TOKEN=你的完整ChannelAccessToken
LINE_USER_ID=你的U開頭UserID
```

## 學生背景私密設定

```powershell
Copy-Item profile.example.json profile.json
code profile.json
```

`profile.json` 只放在本機，已由 `.gitignore` 排除。請填入實際學校、學制、科系、年級、成績、排名、居住地與特殊身分。不要將 `profile.json` 上傳到 GitHub。

範例欄位：

```json
{
  "school": "你的學校",
  "degree_level": "學士",
  "program_type": "進修部",
  "department": "你的科系",
  "year": 2,
  "employed": true,
  "average_grade": 90,
  "conduct_grade": 85,
  "class_rank": 1,
  "class_size": 20,
  "residence": "",
  "special_statuses": [],
  "research_keywords": ["電子", "電力", "能源"]
}
```

## 自動測試與依賴更新

GitHub Actions 會在推送到 `main` 或建立 Pull Request 時自動執行：

```text
Ruff 靜態檢查
→ pytest
→ 測試覆蓋率報告
```

Dependabot 每週檢查 Python 套件與 GitHub Actions 版本，並以 Pull Request 提出更新。

## 執行測試

```powershell
python -m ruff check .
python -m pytest tests/
```

測試使用暫存資料庫與模擬 LINE 回應，不會呼叫真實 LINE API，也不會修改 `data/` 正式資料庫。

## Dry-run：先看哪些公告會被推播

```powershell
python main.py --dry-run
```

Dry-run 會：

- 蒐集公告並保存 `discovered`。
- 下載尚未評估公告的內頁文字。
- 使用 `profile.json` 判斷 `eligible`、`review`、`ineligible`。
- 只列出明確適合且尚未通知的公告。
- 不驗證 LINE Token，不傳送 LINE，不修改 `notified_at`。

若公告內文無法讀取，或資格只存在尚未解析的附件中，狀態會是 `review`，預設不推播。

## 首次上線：建立歷史基準

只執行一次：

```powershell
python main.py --initialize-baseline
```

此模式不讀取 `profile.json`、不驗證 LINE Token，也不傳送 LINE。既有公告會標記為歷史基準，未來新增公告才進入個人化評估。

## 正式模式

```powershell
python main.py
```

正式模式規則：

- 驗證 `.env` 與 `profile.json`。
- 只推播 `eligibility_status = eligible` 的公告。
- `review` 預設不推播；可由 `config.py` 的 `NOTIFY_REVIEW_ITEMS` 調整。
- 摘要中的每筆公告都有日期、標題、符合原因與獨立網址。
- 每則摘要最多列出 `LINE_SUMMARY_BATCH_SIZE` 筆。
- 成功傳送後才寫入該批公告的 `notified_at`。
- 發送失敗時保留 pending，供下次重試。

## 目前規則能力

可明確排除：

- 明確限定日間部，但背景為進修部。
- 明確限定研究所、非大專、新生或應屆畢業等資格。
- 公告明確排除進修部或在職學生。
- 特定家庭或法定身分為必要條件且背景不符。
- 學業平均或操行成績未達門檻。

已降低下列誤判：

- 「日間部及進修部均可申請」不會排除進修部。
- 「大學生及研究生均可申請」不會排除學士生。
- 「清寒學生優先但不限清寒」不會排除一般學生。
- 可辨識「不得低於 80 分」類型的成績門檻。

可確認正向匹配：

- 就讀學校或科系明確相符。
- 電子、電機、電力、能源等背景關鍵字相符。
- 一般大專在校生條件且未發現排除條件。
- 優秀學生型獎學金且成績達基本方向。

目前尚未解析 PDF、Word 等附件內容；附件是唯一資格來源時會標為 `review`，不會直接推播。

## 安全檢查

```powershell
python -m ruff check .
python -m pytest tests/
python main.py --dry-run
git status --ignored
```

確認 `.env`、`profile.json`、`.venv/` 與 `data/*.db` 均未被 Git 追蹤。
