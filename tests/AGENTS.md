# tests/AGENTS.md

## 範圍
本目錄只放測試程式與測試輸出。

## 規則
- 測試不得真的呼叫 LINE API。
- 使用 monkeypatch 或 mock 隔離外部服務。
- 每項核心邏輯至少包含成功案例。
- 測試產出統一放入 `tests/output/`。
- 禁止把測試程式碼放入 `main.py`。
