# AGENTS.md

## 角色
繁體中文 Python 工程師。
修改程式前先說明要做什麼、怎麼拆分、怎麼驗證。

## 開發環境
- Windows 使用 PowerShell。
- 路徑由 `pathlib.Path` 處理。
- 專案必須使用 `.venv`。
- Python 檔案使用 UTF-8。

## 程式規範
- 每個 Python 檔案頂端加入 `# -*- coding: utf-8 -*-`。
- 常數使用全大寫並集中在 `config.py`。
- 函式只處理一件事，原則上控制在 20 行內。
- 類別只封裝相關功能，原則上控制在 30 行內。
- 函式上方使用繁體中文註解。
- 禁止 `import *`。
- 禁止寫死絕對路徑。
- 本機機密資料只放在 `.env`；GitHub Actions 機密資料只放在 repository Secrets。

## 資格判斷規範
- 任一必要資格明確不符時立即 `ineligible`。
- 主要申請辦法、適用對象或必要條件未確認時維持 `review`。
- 成績、排名或領域單一正向條件不得單獨產生 `eligible`。
- 只有 `rules` 類附件可解除主要資格附件未知狀態。
- 表單、證明書、切結書或其他次要附件不得取代主要申請辦法。
- 資格規則語意變更時必須提升 `ELIGIBILITY_RULE_VERSION`，使未推播公告重新評估。

## 外部 AI 規範
- 本機規則優先，只有 `review` 的困難文件才能進入外部 AI。
- 掃描附件優先選擇 `rules` 類主要申請辦法，次要證明與表單不得消耗額度。
- 不得把 `profile.json`、LINE Token 或其他個資送往模型。
- 模型只負責結構化抽取，不得直接決定 `eligible`。
- 每次執行必須有呼叫數、頁數與 Token 上限。
- 相同文件必須依內容雜湊、模型與提示版本使用快取。
- 模型證據不足、頁面不完整或輸出驗證失敗時維持 `review`。
- Audit 必須顯示模型抽取欄位與頁碼證據，供人工核對。

## 雲端排程規範
- GitHub Actions 第一次正式使用前必須明確執行 `initialize` 建立歷史基準。
- 正式排程找不到既有雲端狀態時必須 fail closed，不得自動 baseline 或推播。
- SQLite 狀態上傳 artifact 前必須加密，解密密碼只放 GitHub Actions Secret。
- `profile.json` 只能由 Secret 在 runner 暫時建立，不得提交到 repository 或 artifact。
- 本機排程與雲端排程不得同時正式運作，避免兩份 SQLite 各自重複推播。
- Workflow 必須設定 concurrency，禁止正式流程重疊執行。

## 測試規範
- 修改既有邏輯前先執行 `pytest tests/`。
- 新專案先完成邏輯，再補獨立測試。
- 測試輸出放在 `tests/output/`。
- 所有測試通過後才能完成任務。

## 專案維護
- 規則變更時同步更新本檔。
- 不建立 `_copy`、`_backup` 或編號式版本檔案。
- 任務結束前清除暫存檔。
