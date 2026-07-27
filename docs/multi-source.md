# MultiSourceCollector

第一批接入五個官方來源：

1. 龍華科技大學獎助學金公告
2. 教育部留學獎學金
3. 教育部歐盟獎學金
4. 教育部與世界百大合作設置獎學金
5. 原住民族委員會大專校院獎助學金

## 執行原則

- 來源依上述順序執行；同一公告重複出現時保留優先序較前的來源。
- 單一來源連線、解析或格式錯誤不會中止其餘來源。
- 五個來源全部失敗時才以非零 exit code 結束。
- 每次 audit 與 LINE 真實報告都顯示各來源成功、失敗及去重後筆數。
- `review` 與 `ineligible` 不會推播；正式模式仍只推播 `application + eligible`。

## 跨來源去重

既有 `content_hash` 保留，用於維持目前 SQLite 與通知狀態。新增 `dedup_hash`，由正規化後的公告標題建立，會移除常見的「公告」、「轉知」與版面括號標籤，但保留年度與獎學金名稱。

舊 SQLite 首次開啟時會自動：

1. 新增 `dedup_hash` 欄位。
2. 依既有標題回填去重鍵。
3. 建立非唯一索引。

不會清除 `baseline_at`、`notified_at` 或既有資格結果。

## 驗證

```powershell
python main.py --audit --use-gemini
```

輸出應先列出五個官方來源狀態，再顯示合併、去重後的稽核數量。正式 GitHub Actions 每日 07:30 流程不需要新增 Secrets。
