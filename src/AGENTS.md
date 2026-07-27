# src/AGENTS.md

## 範圍
本目錄只放正式程式邏輯。

## 規則
- Collector、Analyzer、Repository、Notifier 必須分層。
- 函式只做一件事，避免混合網路請求、資料解析與資料保存。
- 外部 API 錯誤必須明確拋出，不得靜默忽略。
- 不得在原始碼內保存 Token、User ID 或密碼。
- 所有路徑使用 `pathlib.Path`。
