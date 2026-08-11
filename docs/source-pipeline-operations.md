# 獎學金來源管線維運

## 系統範圍

正式系統管理 7 個 collector 群組：

1. 龍華科技大學
2. 教育部圓夢助學網－民間團體
3. 教育部圓夢助學網－政府機關
4. 原住民族委員會大專校院獎助學金
5. 教育部留學獎學金
6. 新北市新莊區聯合獎助學金
7. TUN 38 方案官方監測

不同網站保留專用 collector 或來源規則，但全部進入同一條後續流程：

```text
入口抓取
→ 候選公告
→ 方案匹配
→ 正文與附件
→ 申請證據評分
→ 公告分類
→ 申請期間
→ 硬性資格
→ 人工成績／排名確認
→ LINE
```

## 資料欄位

每筆公告至少保留：

- `entry_url`：監控入口。
- `detail_url`：實際正文或附件入口。
- `announcement_id`：來源加正規化正文 URL 的穩定識別。
- `revision_hash`：正文、附件文字與辦法狀態的版本雜湊。
- `program_id`：已知方案識別。
- `match_method`：`exact_alias`、`equivalent_alias` 或 `core_terms`。
- `match_score`：方案匹配分數。
- `detail_evidence_score`：申請正文證據分數。
- `resolution_status`：正文完整、證據不足、錯頁或來源錯誤。
- `notice_kind`：申請、結果、法規、資訊或未知。
- `application_status`：開放、尚未開始、常年、已截止、近期未知或歷史未知。
- `eligibility_status`：硬性條件符合、待確認或不符。
- `manual_checks`：成績、操行、排名、GPA、無不及格等由使用者自行核對的條件。
- `review_kind`：來源不完整、個人資料缺值或語意待確認。

## 資格判斷原則

系統只自動判斷硬性條件，例如：

- 學校、學制、學位、年級。
- 科系或研究領域。
- 國籍、戶籍、特殊身分。
- 進修部、在職生或畢業年級排除。
- 推薦、申請對象與其他必要身分。

以下條件只抽取並顯示，不自動決定符合或不符：

- 學業平均、學期成績、操行。
- 班級排名、系排名、GPA。
- 是否有不及格科目。

`eligible` 的意思是「硬性條件符合」，不代表成績與排名已由系統確認。

## 申請期間

- `open`：目前開放。
- `upcoming`：尚未開始。
- `evergreen`：全年或長期受理。
- `expired`：已截止，不列為個人資格不符。
- `deadline_unknown`：近期公告但期限尚未解析。
- `stale_unknown`：舊公告且沒有當年度申請證據，不進可申請通知。

## 公告版本

第一次建立 `revision_hash` 只建立基準，不重送舊通知。

正文、附件文字或辦法狀態實質改變時：

1. 清除舊資格結果。
2. 重新判斷公告與期限。
3. 重新判斷硬性資格。
4. 改版後仍可申請且硬性條件符合時，重新進入 LINE 通知生命週期。

空白、query 順序、追蹤參數與附件順序變化不視為實質改版。

## 正文抽取政策

HTML 正文使用版本化 extraction policy：

- `default-html`：一般網站。
- `lhu-html`：龍華公告。
- `auden-html`：耀登公告。

稽核會保存：

- policy 名稱與版本。
- policy hash。
- 實際 selector。
- 是否使用 heuristic fallback。

新增特殊網站時，優先增加來源專屬 policy 與 fixture，不放寬全域 selector。

## 來源健康與排除紀錄

完整 LINE audit 會輸出：

- `structured-shadow-audit.csv`
- `structured-shadow-audit.json`
- `source-health.json`
- `pipeline-rejections.json`

`source-health.json` 包含每個來源的健康分數、完整性、頁面成功率、解析率與 TUN 逐方案狀態。

`pipeline-rejections.json` 保存每筆排除的來源、方案、標題、入口、正文 URL、管線階段與原因。

## 自動化

### LINE production audit

由 `.github/line-report-trigger` 變更觸發：

```text
還原加密 SQLite
→ 建立私密 profile
→ 完整 audit
→ 傳送 LINE
→ 上傳四個 audit artifacts
→ 加密回存 SQLite
→ 清除 profile
```

### 每週來源契約

`.github/workflows/source-contract.yml` 每週日臺北時間約 02:00 執行完整來源契約：

- 不需要 profile、Gemini 或 LINE Secret。
- 不修改正式 SQLite。
- 任一來源抓取失敗或分頁不完整時，workflow 失敗。
- 永遠上傳 `source-health.json` 與執行 log。

## 維護優先順序

1. 先看 `source-health.json` 定位來源失敗。
2. 再看 `pipeline-rejections.json` 定位公告消失階段。
3. 正文不足時檢查 extraction policy 與 selector。
4. 方案漏抓時檢查 match method、alias、核心詞與分數。
5. 期限錯誤時檢查原文日期語境，不直接放寬全域日期規則。
6. Structured shadow 只作比較與抽取輔助，本機規則仍是正式資格決策者。
