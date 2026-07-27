# 程式設計規範

## 分層

```text
Collector
→ Normalizer
→ Repository
→ Analyzer
→ Notifier
```

目前第一階段只實作 Notifier。

## 核心原則

- 網頁抓取、AI 分析、SQLite 與 LINE 傳送不得混在同一函式。
- 確定性工作由 Python 與資料庫負責。
- AI 只負責語意抽取、資格比對與摘要。
- 外部 API 必須設定 timeout。
- 機密資料由 `.env` 載入。
