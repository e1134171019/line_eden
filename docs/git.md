# Git 操作規範

## 初始化

```powershell
git init
git add .
git commit -m "chore: 建立 LINE 推播測試骨架"
```

## 功能開發

不要直接在 `main` 修改正式功能：

```powershell
git switch main
git pull origin main
git switch -c feat/功能名稱
```

完成後推送功能分支並建立 Pull Request：

```powershell
git push -u origin feat/功能名稱
```

## 提交前

```powershell
python -m ruff check .
python -m pytest tests/ --cov=src --cov-report=term-missing
git status --ignored
```

確認下列私密或暫存資料沒有被提交：

- `.env`
- `profile.json`
- `.venv/`
- `data/*.db`
- `logs/`
- `temp/`
- `tests/output/`

## Pull Request 合併條件

- GitHub Actions 的 Python 3.11 與 3.13 工作都通過。
- Ruff 無錯誤。
- pytest 全部通過。
- 沒有修改或輸出 `.env`、`profile.json` 與正式 SQLite。
- 資格判斷規則變更時，必須同步更新匿名化 fixture。

## Commit 類型

- `feat`：新增功能
- `fix`：修正錯誤
- `test`：新增或修改測試
- `docs`：文件
- `chore`：環境與專案維護
- `ci`：GitHub Actions 與自動化流程
