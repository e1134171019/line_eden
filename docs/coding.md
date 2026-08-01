# 程式設計規範

## 分層

```text
Collector
→ Detail Fetcher
→ Model / Normalizer
→ Profile Loader
→ Eligibility Evaluator
→ Repository
→ Formatter
→ Notifier
```

## 核心原則

- 公告列表抓取、公告內頁讀取、資格判斷、SQLite 與 LINE 傳送必須分層。
- 確定性狀態由 Python 與 SQLite 負責。
- `eligible` 才進入預設推播清單。
- `review` 與 `ineligible` 保留判斷狀態，但預設不推播。
- LINE 成功後才能寫入 `notified_at`。
- 背景設定變更時，使用背景指紋重新評估尚未通知公告。
- 公告 identity 只使用來源與正規化網址；listing metadata 不得作為穩定 ID。
- `revision_hash` 只反映正文、附件與辦法狀態；抽取 policy hash 必須分開保存。
- 來源專屬正文範圍以版本化 policy 設定，找不到 strict selector 時採失敗關閉。
- 外部 HTTP 請求必須設定 timeout 並明確處理錯誤。
- LINE 憑證放在 `.env`。
- 學生背景放在 `profile.json`。
- `.env` 與 `profile.json` 都不得提交到 GitHub 或輸出至 log。
