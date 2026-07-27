# Scholarship Agent

第一階段只驗證 LINE Messaging API 推播。  
獎學金來源蒐集、SQLite 去重與 AI 資格分析會在 LINE 推播確認成功後加入。

## 專案結構

```text
scholarship-agent/
├── AGENTS.md
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── config.py
├── main.py
├── src/
│   ├── AGENTS.md
│   ├── __init__.py
│   └── notifiers/
│       ├── __init__.py
│       └── line_notifier.py
├── tests/
│   ├── AGENTS.md
│   ├── output/
│   └── test_line_notifier.py
├── docs/
│   ├── coding.md
│   └── git.md
├── logs/
└── temp/
```

## Windows PowerShell 安裝

```powershell
cd scholarship-agent
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

若 PowerShell 阻擋虛擬環境啟用，可在目前視窗暫時執行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
./.venv/Scripts/Activate.ps1
```

## 建立環境變數

```powershell
Copy-Item .env.example .env
notepad .env
```

將 `.env` 改成：

```dotenv
LINE_CHANNEL_ACCESS_TOKEN=你的完整ChannelAccessToken
LINE_USER_ID=你的U開頭UserID
```

不要將 `.env` 上傳到 GitHub。

## 環境確認

```powershell
python --version
pip --version
pytest --version
```

## 執行測試

```powershell
pytest tests/
```

測試使用模擬回應，不會真的傳送 LINE 訊息。

## 傳送第一則測試訊息

```powershell
python main.py
```

成功時終端機會顯示：

```text
LINE 測試訊息已送出，請檢查手機 LINE。
```
