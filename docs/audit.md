# Audit 診斷說明

執行：

```powershell
python main.py --audit 2>&1 |
  Tee-Object "tests/output/audit-diagnostics.txt"
```

每筆公告會顯示：

```text
來源診斷：success | html | text/html | 12.5 KiB | 文字 680 字
附件診斷：發現 4，嘗試 3，成功 1，失敗 2
  [1] success | pdf | application/pdf | 320.4 KiB | 文字 1824 字
      請求：https://example.com/rules.pdf
      最終：https://cdn.example.com/rules.pdf
  [2] error | unknown | text/html | 0 B | 文字 0 字
      請求：https://example.com/download
      錯誤：HTTPStatusError: 403 Forbidden
```

欄位定義：

- `發現`：公告正文區塊中辨識到的支援附件總數。
- `嘗試`：安全上限內實際下載解析的附件數量。
- `成功`：成功取得文字的附件數量。
- `失敗`：下載、格式辨識或文字解析失敗的附件數量。
- `請求`：公告原始附件網址。
- `最終`：HTTP 重新導向後的實際網址，只在網址改變時顯示。
- `文字`：實際送入資格判斷的擷取文字長度。

Audit 不傳送 LINE，也不修改 SQLite 的 baseline、notified 或資格狀態。
