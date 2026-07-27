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

開發與測試環境改用：

```powershell
python -m pip install -r requirements-dev.txt
```

`requirements.txt` 只保留正式執行需要的套件；pytest、coverage 與 Ruff 集中在 `requirements-dev.txt`。

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
  "residence": "新北市",
  "special_statuses": [],
  "research_keywords": ["電子", "電力", "能源"]
}
```

## 本機品質檢查

```powershell
python -m ruff check .
python -m pytest tests/ --cov=src --cov-report=term-missing
```

測試使用暫存資料庫與模擬 LINE 回應，不會呼叫真實 LINE API，也不會修改 `data/` 正式資料庫。

## GitHub 自動檢查

`.github/workflows/quality.yml` 會在 push 與 Pull Request 時，使用 Python 3.11、3.13 執行：

```text
安裝 requirements-dev.txt
→ Ruff 靜態檢查
→ pytest + coverage
```

`.github/dependabot.yml` 每週檢查 pip 與 GitHub Actions 依賴更新。

建議在 GitHub 的 `Settings → Branches` 對 `main` 啟用：

- Require a pull request before merging
- Require status checks to pass before merging
- 將 `test (3.11)`、`test (3.13)` 設為必要檢查
- Block force pushes
- Block branch deletion

這些倉庫管理設定需要由 GitHub 網頁啟用，程式檔案本身無法代替 Branch Protection。

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

- 日間部限定，但背景為進修部。
- 研究所、非大專、新生或應屆畢業等明確年級限制。
- 公告明確排除進修部或在職學生。
- 特定家庭或法定身分與背景不符。
- 學業平均、操行成績或班級排名未達門檻。
- 戶籍限制與 `profile.json` 不符。

已降低的常見誤判：

- 「日間部及進修部皆可申請」不會因出現日間部而排除。
- 「大學生及研究生皆可申請」不會因出現研究生而排除。
- 「清寒學生優先，非清寒亦可」不會把清寒誤當必要資格。
- 支援「不得低於」「至少」「須達」等成績門檻句型。
- 支援班排名前 N 名、前 N% 與臺／台異體字戶籍比對。

可確認正向匹配：

- 就讀學校或科系明確相符。
- 電子、電機、電力、能源等背景關鍵字相符。
- 一般大專在校生條件且未發現明確排除條件。
- 成績、排名、戶籍或進修部資格明確符合。

匿名化規則案例集中在 `tests/fixtures/eligibility_cases.json`，新增規則或修正網站解析時應同步補案例。

目前尚未解析 PDF、Word 等附件內容；附件是唯一資格來源時會標為 `review`，不會直接推播。

## 安全檢查

```powershell
python -m ruff check .
python -m pytest tests/
python main.py --dry-run
git status --ignored
```

確認 `.env`、`profile.json`、`.venv/` 與 `data/*.db` 均未被 Git 追蹤。
