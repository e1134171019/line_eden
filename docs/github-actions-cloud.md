# GitHub Actions 雲端排程

此模式不依賴本機開機。GitHub Actions 每天以雲端 runner 執行 Scholarship Agent，台灣時間設定為 07:30。

## 執行架構

```text
GitHub Actions schedule（23:30 UTC）
→ 台灣時間翌日 07:30
→ 還原上一輪加密 SQLite artifact
→ 由 GitHub Secrets 建立 profile.json
→ python main.py --use-gemini
→ 只有 application + eligible 才傳 LINE 與可選的 Apprise 管道
→ 加密並保存更新後 SQLite 狀態
```

GitHub runner 每次都是全新環境，因此不能直接依賴本機 `data/`。雲端版使用加密 artifact 保存：

```text
data/scholarships.db
data/gemini_cache.db（存在時）
```

狀態先以 GPG AES-256 對稱加密，再上傳為 `scholarship-agent-state` artifact。解密密碼只放在 GitHub Actions Secret。

## 必要 GitHub Actions Secrets

進入 repository：

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

建立以下五個 Secrets：

```text
LINE_CHANNEL_ACCESS_TOKEN
LINE_USER_ID
GEMINI_API_KEY
STUDENT_PROFILE_B64
STATE_PASSPHRASE
```

前三個值與本機 `.env` 相同，不要貼到 Issue、Commit、README 或 Actions log。

若要啟用額外通知管道，可再建立一個選填 Secret：

```text
APPRISE_URLS
```

值的格式與本機 `.env` 相同，可用空白或換行分隔多個 Apprise URL。URL 通常含有
bot token、webhook token 或密碼，不得寫進 workflow、Issue、Commit 或 Actions log。
沒有設定此 Secret 時仍只傳 LINE，不影響既有流程。

### 產生 STUDENT_PROFILE_B64

在本機專案根目錄執行：

```powershell
$ProfileB64 = [Convert]::ToBase64String(
  [IO.File]::ReadAllBytes((Resolve-Path "profile.json"))
)
$ProfileB64 | Set-Clipboard
```

接著新增 `STUDENT_PROFILE_B64` Secret，直接貼上剪貼簿內容。

Base64 只用來把 JSON 轉成單行文字，本身不是加密；機密性來自 GitHub Actions Secret。

### 產生 STATE_PASSPHRASE

```powershell
$Bytes = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
$StatePassphrase = [Convert]::ToBase64String($Bytes)
$StatePassphrase | Set-Clipboard
```

新增 `STATE_PASSPHRASE` Secret 後，將相同值另外保存在密碼管理器。若遺失或更換此密碼，舊的狀態 artifact 將無法解密，需要重新建立雲端基準。

## 第一次啟用：建立雲端歷史基準

Workflow 合併到 `main` 並完成 Secrets 後：

```text
Actions
→ Scholarship cloud schedule
→ Run workflow
→ operation：initialize
→ Run workflow
```

`initialize` 只執行：

```text
python main.py --initialize-baseline
```

它會將目前公告設成雲端歷史基準，不讀取 `profile.json`，也不傳送 LINE。成功後應產生 `scholarship-agent-state` artifact。

這一步必須先完成。正式 `run` 找不到雲端狀態時會直接失敗，不會自動把全部歷史公告當成新公告。

## 測試手機 LINE 通知

在同一個 workflow 手動選擇：

```text
operation：test-line
```

手機應收到：

```text
GitHub Actions 雲端測試：Eden 獎學金助手：LINE Messaging API 測試成功。
```

此模式不讀寫 SQLite，也不呼叫 Gemini。

## 手動驗證正式流程

建立基準與 LINE 測試成功後，再手動選擇：

```text
operation：run
```

目前若沒有新公告，應顯示通知數量 0，並產生新一版加密狀態 artifact。

也可選擇：

```text
operation：dry-run
```

此模式會使用雲端狀態與 Gemini 評估新公告，但不傳送 LINE。

## 每日排程

Workflow cron：

```yaml
cron: "30 23 * * *"
```

GitHub Actions schedule 使用 UTC；23:30 UTC 對應台灣翌日 07:30。排程可能因 GitHub runner 負載延後數分鐘，不能視為精確到秒的即時系統。

## 狀態保存與失敗處理

每次 `initialize`、`run` 或 `dry-run` 後，workflow 都會嘗試保存當下 SQLite 狀態，包括 Agent 最後回傳非零 exit code 的情況。通知層也會逐管道保存成功紀錄，可降低部分管道已成功、後續管道或程序失敗時再次重複通知的風險。

保存內容：

```text
artifact：scholarship-agent-state
檔案：scholarship-state.tar.gz.gpg
保留：90 天
```

每天成功執行會產生新的狀態 artifact，因此正常情況下始終有近期狀態可還原。

每次執行另保存：

```text
scholarship-agent-log-<run_id>
```

log 保留 30 天，不包含 `profile.json` 或 Secret 原文。

## 避免本機與雲端重複執行

雲端 `initialize`、`test-line`、手動 `run` 都成功後，移除本機 Windows 排程：

```powershell
& "./scripts/remove-scholarship-task.ps1"
```

本機程式與資料庫可保留，供 audit、測試與開發使用。不要讓本機排程和 GitHub Actions 同時執行正式模式，否則兩邊使用不同 SQLite 狀態，可能對同一則新公告各推播一次。

## 安全邊界

- Workflow 權限只有 `contents: read` 與 `actions: read`。
- `profile.json` 只在 runner 暫時建立，執行結束後 runner 被銷毀。
- SQLite artifact 上傳前使用 GPG AES-256 加密。
- 找不到狀態時正式排程 fail closed。
- concurrency group 禁止兩個正式雲端流程同時執行。
- 不增加 Gemini 呼叫數、頁數或 Token 上限。
- Pull Request 與一般 push 不會執行正式 Scholarship Agent。
