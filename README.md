# Scholarship Agent

目前包含六個階段：

1. LINE Messaging API 推播。
2. 龍華獎學金公告蒐集、SQLite 去重、歷史基準與 dry-run。
3. 讀取公告主內容，依本機私密學生背景判斷適合度。
4. 先區分申請型、法規型、結果型與資訊型，只推播申請型且明確適合的公告。
5. 追蹤短網址並解析 PDF、DOCX 附件，降低資格只寫在附件造成的漏報。
6. 明確啟用時，只把本機無法解析的掃描型 PDF 少量頁面交給 Gemini 抽取資格欄位。

## 核心流程

```text
公告列表
→ 公告主內容擷取
→ 短網址重新導向
→ PDF／DOCX 附件文字
→ notice_kind 公告用途分類
→ 本機個人背景資格判斷
├─ ineligible：結束，不呼叫 Gemini
├─ eligible：可推播
└─ review
   └─ 掃描型 PDF + --use-gemini
      → 只傳前 N 頁
      → Gemini JSON Schema 抽取
      → 本機 EligibilityEvaluator 重新判斷
```

公告正文擷取會排除頁首、導覽列、活動橫幅、側欄、表單與頁尾，避免「電子郵件」、「電子工程系導覽」及共用活動圖片說明污染資格判斷。

附件成功解析後，網頁中的「申請資格請參閱附件」不再自動造成 `review`。附件無法下載、格式不支援、超過安全上限或沒有可擷取文字時，仍採保守不推播。

Gemini 不接收 `profile.json`、LINE Token 或 User ID。模型只抽取文件條件，最後的 `eligible`、`review`、`ineligible` 仍由本機規則決定。

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

## Gemini 私密設定

Gemini 預設不會啟用。只有命令列明確加入 `--use-gemini` 時，程式才會驗證 API Key 並建立 client。

`.env` 可加入：

```dotenv
GEMINI_API_KEY=你的GeminiAPIKey
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_MAX_CALLS_PER_RUN=3
GEMINI_MAX_INPUT_TOKENS_PER_RUN=12000
GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT=5000
GEMINI_MAX_OUTPUT_TOKENS=1200
GEMINI_MAX_PAGES_PER_DOCUMENT=2
```

安全邊界：

- 只有 `application + review` 且附件被確認為掃描型 PDF 才會進入 Gemini。
- 本機已能判定 `ineligible` 或 `eligible` 時不呼叫 Gemini。
- 每個公告最多選一個掃描附件。
- PDF 預設只重組前 2 頁，不上傳整份文件。
- 生成前呼叫 `count_tokens`，超過單份或單次預算即維持 `review`。
- 達到呼叫數上限後，後續公告連 `count_tokens` 都不再呼叫。
- 模型必須回傳符合 JSON Schema 的資格欄位與頁碼證據。
- 頁面不足、不是完整辦法、沒有證據或輸出驗證失敗時維持 `review`。

相同附件使用下列資料建立快取鍵：

```text
SHA-256(完整附件內容) + Gemini model + prompt version
```

快取位於：

```text
data/gemini_cache.db
```

快取不保存 `profile.json`。相同文件再次執行時仍會下載以確認內容雜湊，但不會再次產生 Gemini Token。

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

`special_statuses` 可使用「低收入戶」、「中低收入戶」、「失業勞工子女」等正式名稱。系統也會辨識公告中的「低收」、「中低收」等常見同義詞。

## 自動測試與依賴更新

GitHub Actions 會在推送到 `main` 或建立 Pull Request 時自動執行：

```text
Ruff 靜態檢查
→ pytest
→ 測試覆蓋率報告
```

Gemini 測試使用 client 替身與暫存 SQLite，不會呼叫真實 Gemini API。

Dependabot 每週檢查 Python 套件與 GitHub Actions 版本，並以 Pull Request 提出更新。

## 執行測試

```powershell
python -m ruff check .
python -m pytest tests/
```

測試使用暫存資料庫、MockTransport 與模擬 LINE／Gemini 回應，不會呼叫真實外部 API，也不會修改 `data/` 正式資料庫。

## Audit：重新檢查全部公告

一般 audit 完全不呼叫 Gemini：

```powershell
python main.py --audit
```

Audit 會：

- 重新抓取目前列表中的全部公告。
- 重新擷取公告主內容與可解析附件。
- 顯示 `notice_kind`、資格狀態、判斷原因與文字摘要。
- 不驗證 LINE Token。
- 不傳送 LINE。
- 不修改獎學金的 `baseline_at`、`notified_at` 或資格狀態。

明確測試 Gemini 備援：

```powershell
python main.py --audit --use-gemini
```

此模式仍不修改獎學金狀態，但會將文件 Gemini 結果寫入獨立 `data/gemini_cache.db`。每次最多呼叫 `.env` 設定的數量，其他公告維持 `review`。

## Dry-run：先看哪些新公告會被推播

不使用 Gemini：

```powershell
python main.py --dry-run
```

對尚未評估的新公告啟用受限 Gemini：

```powershell
python main.py --dry-run --use-gemini
```

Dry-run 會：

- 蒐集公告並保存 `discovered`。
- 只處理尚未評估公告的主內容與附件。
- 使用 `profile.json` 判斷 `eligible`、`review`、`ineligible`。
- 只列出 `application + eligible` 且尚未通知的公告。
- 不驗證 LINE Token，不傳送 LINE，不修改 `notified_at`。
- 顯示 Gemini 生成呼叫、快取命中及 input／output Token。

若公告正文、支援附件與受限 Gemini 都無法提供可靠資格，狀態會是 `review`，預設不推播。

## 首次上線：建立歷史基準

只執行一次：

```powershell
python main.py --initialize-baseline
```

此模式不讀取 `profile.json`、不驗證 LINE Token，也不傳送 LINE。建立基準時禁止搭配 `--use-gemini`。

## 正式模式

不使用 Gemini：

```powershell
python main.py
```

對新公告啟用受限 Gemini：

```powershell
python main.py --use-gemini
```

正式模式規則：

- 驗證 `.env` 與 `profile.json`。
- 使用 Gemini 時另驗證 `GEMINI_API_KEY`。
- 只推播 `notice_kind = application` 且 `eligibility_status = eligible` 的公告。
- 法規修正、獲獎名單、說明會與用途不明公告不推播。
- `review` 預設不推播；可由 `config.py` 的 `NOTIFY_REVIEW_ITEMS` 調整。
- 摘要中的每筆公告都有日期、標題、符合原因與獨立網址。
- 每則摘要最多列出 `LINE_SUMMARY_BATCH_SIZE` 筆。
- 成功傳送後才寫入該批公告的 `notified_at`。
- 發送失敗時保留 pending，供下次重試。

## 公告用途分類

```text
application：目前可申請或申辦
policy：辦法、要點、條文或法規修正
result：獲獎、錄取或核定名單
information：說明會、提醒或一般資訊
unknown：訊號不足，採保守不推播
```

只有 `application` 會進入個人資格比對。

## 附件解析能力

目前支援：

- 短網址 HTTP 重新導向。
- 一般 HTML 申請頁。
- 文字型 PDF。
- DOCX 段落與表格。
- 明確啟用時，以 Gemini 視覺理解掃描型 PDF 的前 N 頁。
- 每則公告依價值排序後最多解析 3 個附件。
- 單一下載資源上限 10 MiB。
- 本機 PDF 最多解析前 40 頁。

目前仍保守處理：

- 舊版二進位 `.doc`。
- 掃描型 PDF 前 N 頁沒有完整資格。
- 需要登入、驗證碼或 JavaScript 才能取得的附件。
- XLS／XLSX 及壓縮檔內的資格內容。

上述情況不會直接推播，會保留為 `review`。

## 目前規則能力

可明確排除：

- 明確限定日間部，但背景為進修部。
- 明確限定研究所、非大專、新生或應屆畢業等資格。
- 公告明確排除進修部或在職學生。
- 特定家庭或法定身分為必要條件且背景不符。
- 「低收」、「中低收」、「失業勞工子女」等身分同義詞不符。
- 學業平均、操行成績或排名未達門檻。

已降低下列誤判：

- 「日間部及進修部均可申請」不會排除進修部。
- 「大學生及研究生均可申請」不會排除學士生。
- 「清寒學生優先但不限清寒」不會排除一般學生。
- 「電子郵件」與網站導覽不會視為電子工程背景。
- 專業領域必須出現在標題或科系、學系、領域、主修等資格語境中。
- 可辨識「不得低於 80 分」類型的成績門檻。
- Gemini 的同類學制與學位對象會合併成同一句，再交給本機規則判斷。

## 安全檢查

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest tests/
python main.py --audit
python main.py --audit --use-gemini
python main.py --dry-run
python main.py --dry-run --use-gemini
git status --ignored
```

確認 `.env`、`profile.json`、`.venv/` 與 `data/*.db` 均未被 Git 追蹤。
