# Windows 自動排程

Scholarship Agent 可由 Windows 工作排程器每天執行正式模式。排程處理尚未基準化的新公告，也會比較仍在來源列表中的公告 revision。`review` 與 `ineligible` 不會推播；已通知公告只有在正文或附件實質改版、重新評估後仍為 `eligible` 時才會再次推播。

## 自動化組成

```text
scripts/run-scholarship-agent.ps1
→ .venv/Scripts/python.exe
→ python -m src.automation.scheduled_runner
→ python main.py --use-gemini
```

排程啟動器會：

- 使用專案自己的 `.venv`，不依賴目前 PowerShell 是否已啟用虛擬環境。
- 建立 `data/scholarship-agent.lock`，防止重複同時執行。
- 六小時以上的殘留鎖視為前次異常中斷，可在下一次執行時清除。
- 每次建立獨立的 `logs/run-YYYYMMDD-HHMMSS.log`。
- 原子更新 `data/last_run.json`，記錄成功、失敗、exit code 與摘要數字。
- 子程序回傳非零 exit code 時，工作排程器可看見失敗結果。

`logs/`、`data/*.db`、`.env` 與 `profile.json` 均不會提交到 GitHub。

## PowerShell 版本

腳本同時支援 Windows PowerShell 5.1 與 PowerShell 7。不要在已開啟的 PowerShell 終端內再次輸入 `powershell ...`；直接用呼叫運算子 `&` 執行腳本即可。

安裝排程時，程式會取得目前執行中的 PowerShell host 路徑：

```text
Windows PowerShell 5.1 → powershell.exe
PowerShell 7 → pwsh.exe
```

工作排程器會保存這個完整路徑，不再寫死 `powershell.exe`。

## 安裝前檢查

在專案根目錄執行：

```powershell
Set-Location C:/scholarship-agent
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

Test-Path .venv/Scripts/python.exe
Test-Path .env
Test-Path profile.json

python -m pytest tests/
python main.py --use-gemini
```

三個 `Test-Path` 都應顯示 `True`，正式模式也應能正常結束。

## 手動測試排程啟動器

```powershell
& "./scripts/run-scholarship-agent.ps1"
```

此指令會執行正式模式，可能在發現 `eligible` 新公告時傳送 LINE。測試完成後檢查：

```powershell
Get-Content data/last_run.json -Raw
Get-ChildItem logs | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

不使用 Gemini 的測試方式：

```powershell
& "./scripts/run-scholarship-agent.ps1" -NoGemini
```

## 建立每日工作排程

以下範例每天上午 8:00 執行：

```powershell
& "./scripts/install-scholarship-task.ps1" `
  -DailyAt "08:00" `
  -RunNow
```

參數：

- `-DailyAt "HH:mm"`：每日執行時間，24 小時制。
- `-TaskName "ScholarshipAgent"`：自訂工作排程名稱。
- `-NoGemini`：排程正式執行時不加入 `--use-gemini`。
- `-RunNow`：建立完成後立即要求執行一次。

安裝腳本使用目前 Windows 帳號、`RunLevel Limited`，且設定：

- 電腦錯過原定時間時，在可執行後補跑。
- 前一個程序尚未結束時忽略新實例。
- 單次最長執行兩小時。

目前設定為使用者登入 Windows 時執行，不會儲存 Windows 密碼。

## 查看狀態

```powershell
& "./scripts/show-scholarship-task-status.ps1"
```

它會顯示：

- 工作排程目前狀態。
- 上次與下次執行時間。
- Windows Task Scheduler 上次結果。
- `data/last_run.json` 中的 Agent 狀態與摘要。

也可直接查看：

```powershell
Get-ScheduledTask -TaskName ScholarshipAgent
Get-ScheduledTaskInfo -TaskName ScholarshipAgent
Get-Content data/last_run.json -Raw
```

`LastTaskResult = 0` 代表排程入口正常結束。若非 0，先查看 `last_run.json` 指向的 log。

## 移除工作排程

```powershell
& "./scripts/remove-scholarship-task.ps1"
```

移除排程不會刪除：

```text
.env
profile.json
data/scholarships.db
data/gemini_cache.db
data/last_run.json
logs/
```

## 變更執行時間

重新執行安裝腳本即可覆蓋同名排程：

```powershell
& "./scripts/install-scholarship-task.ps1" `
  -DailyAt "19:30"
```

## 故障排查

### `powershell` 不是可辨識的命令

你很可能正在使用 PowerShell 7，其命令名稱是 `pwsh`。在目前終端直接執行腳本即可：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "./scripts/run-scholarship-agent.ps1"
```

也可確認目前 host：

```powershell
(Get-Process -Id $PID).Path
```

### 找不到虛擬環境 Python

```powershell
python -m venv .venv
& ./.venv/Scripts/Activate.ps1
python -m pip install -r requirements.txt
```

### 工作排程存在但沒有執行

```powershell
Get-ScheduledTask -TaskName ScholarshipAgent
Get-ScheduledTaskInfo -TaskName ScholarshipAgent
Start-ScheduledTask -TaskName ScholarshipAgent
```

### last_run.json 顯示 failed

依 `log_file` 欄位開啟對應日誌：

```powershell
$Status = Get-Content data/last_run.json -Raw | ConvertFrom-Json
Get-Content $Status.log_file -Raw
```

### 顯示已在執行

代表 `data/scholarship-agent.lock` 存在。先確認沒有正在執行的 Python 程序，不要在程序仍執行時手動刪鎖。異常中斷留下的鎖超過六小時後會自動清除。
