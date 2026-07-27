# Scholarship Agent

目前包含五個階段：

1. LINE Messaging API 推播。
2. 龍華獎學金公告蒐集、SQLite 去重、歷史基準與 dry-run。
3. 讀取公告主內容，依本機私密學生背景判斷適合度。
4. 先區分申請型、法規型、結果型與資訊型，只推播申請型且明確適合的公告。
5. 追蹤短網址並解析 PDF、DOCX 附件，降低資格只寫在附件造成的漏報。

## 核心流程

```text
公告列表
→ 公告主內容擷取
→ 短網址重新導向
→ PDF／DOCX 附件文字
→ notice_kind 公告用途分類
→ 個人背景資格判斷
→ application + eligible：可推播
→ review：條件不足，預設不推播
→ policy / result / information / unknown：不推播
```

公告正文擷取會排除頁首、導覽列、活動橫幅、側欄、表單與頁尾，避免「電子郵件」、「電子工程系導覽」及共用活動圖片說明污染資格判斷。

附件成功解析後，網頁中的「申請資格請參閱附件」不再自動造成 `review`。附件無法下載、格式不支援、超過安全上限或沒有可擷取文字時，仍採保守不推播。

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

`special_statuses` 可使用「低收入戶」、「中低收入戶」、「失業勞工子女」等正式名稱。系統也會辨識公告中的「低收」、「中低收」等常見同義詞。

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

測試使用暫存資料庫、MockTransport 與模擬 LINE 回應，不會呼叫真實 LINE API，也不會修改 `data/` 正式資料庫。

## Audit：重新檢查全部公告

```powershell
python main.py --audit
```

Audit 會：

- 重新抓取目前列表中的全部公告。
- 重新擷取公告主內容與可解析附件。
- 顯示 `notice_kind`、資格狀態、判斷原因與文字摘要。
- 不驗證 LINE Token。
- 不傳送 LINE。
- 不修改 `baseline_at`、`notified_at` 或其他資料庫內容。

適合在更新正文擷取、附件解析或資格規則後，用現有歷史公告進行回歸檢查。

## Dry-run：先看哪些新公告會被推播

```powershell
python main.py --dry-run
```

Dry-run 會：

- 蒐集公告並保存 `discovered`。
- 只處理尚未評估公告的主內容與附件。
- 使用 `profile.json` 判斷 `eligible`、`review`、`ineligible`。
- 只列出 `application + eligible` 且尚未通知的公告。
- 不驗證 LINE Token，不傳送 LINE，不修改 `notified_at`。

若公告正文與支援附件都無法提供可靠資格，狀態會是 `review`，預設不推播。

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
- 每則公告依價值排序後最多解析 3 個附件。
- 單一下載資源上限 10 MiB。
- PDF 最多解析前 40 頁。

目前不支援：

- 舊版二進位 `.doc`。
- 掃描圖片型 PDF 的 OCR。
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

## 安全檢查

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest tests/
python main.py --audit
python main.py --dry-run
git status --ignored
```

確認 `.env`、`profile.json`、`.venv/` 與 `data/*.db` 均未被 Git 追蹤。
