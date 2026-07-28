# CLI 與服務安全邊界

## 執行模式

程式使用明確的 `RunMode`：

- `live`：允許正式 LINE notifier。
- `dry_run`：完整評估，但 notifier 為 no-op。
- `audit`：完整稽核與 structured shadow，但 notifier 為 no-op。
- `initialize_baseline`：使用獨立 `BaselineService`，不載入 profile、Gemini 或 LINE。

新增 CLI 模式時，必須在 `RunMode`、參數解析與執行分派中明確登記；不得以「不是其他模式就視為 live」推定。

## 通知安全

正式 LINE notifier 只能由 `build_notifier(RunMode.LIVE)` 建立。非 live 模式一律注入 `discard_notification`，即使服務流程誤呼叫 notifier，也不會傳出訊息。

`NOTIFY_REVIEW_ITEMS` 由環境變數控制，預設為 `false`。正式推薦仍限制為 `application + eligible`。

## 附件證據

正式擷取流程使用：

- `NoticeContent.main_text`
- `NoticeContent.attachments`
- `NoticeContent.rules_status`

附件狀態不再依靠在正文中插入 `【附件內容】` 或 `【附件未解析】`。舊 marker 僅可用於歷史測試、舊快取或序列化相容；collector、evaluator 與正式通知決策不得讀取 marker 來推定附件是否完整。

## 品質門檻

Pull Request 必須同時通過：

- Ruff
- strict Pyright
- pytest
- Python 3.11
- Python 3.13
