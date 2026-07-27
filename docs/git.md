# Git 操作規範

## 初始化

```powershell
git init
git add .
git commit -m "chore: 建立 LINE 推播測試骨架"
```

## 提交前

```powershell
pytest tests/
git status
```

確認 `.env`、`logs/`、`temp/` 與 `tests/output/` 沒有被提交。

## Commit 類型

- `feat`：新增功能
- `fix`：修正錯誤
- `test`：新增或修改測試
- `docs`：文件
- `chore`：環境與專案維護
