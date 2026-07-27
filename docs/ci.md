# 持續整合規範

## 自動檢查

GitHub Actions 會在 `main`、功能分支 push 與 Pull Request 時執行：

```text
Python 3.11 / 3.13
→ 安裝 requirements-dev.txt
→ Ruff
→ pytest
→ coverage
```

## 合併門檻

- Ruff 必須通過。
- pytest 必須全部通過。
- `src/` 整體測試覆蓋率不得低於 85%。
- 測試不得使用真實 LINE API、`.env`、`profile.json` 或正式 SQLite。

## 失敗日誌

pytest 失敗時，工作流程會保存七天的測試日誌 artifact。成功時不保留 artifact，避免累積不必要的儲存空間。

## Branch Protection

在 GitHub 網頁的 `Settings → Branches` 對 `main` 設定：

- Require a pull request before merging
- Require status checks to pass before merging
- Require `test (3.11)`
- Require `test (3.13)`
- Block force pushes
- Block branch deletion
