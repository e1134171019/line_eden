# 方案來源監測契約

## 七階段

1. 以 30 個 `ScholarshipProgramWatch` 保存準確入口與來源型態。
2. 透過 `ProgramEntryCrawler` 分流列表與單頁來源；動態頁未命中時失敗關閉。
3. 詳情頁最多追蹤兩層附件，保留每個下載與解析診斷。
4. 完整稽核必須逐方案命中別名並建立公告，才可進入跨來源去重。
5. 跨來源去重包含申請年度，同名不同年度不得合併。
6. 每日增量補抓前兩頁；固定網址以 `revision_hash` 追蹤實質內容改變。
7. 下列驗收情境全部通過後，來源資料才可供資格判斷與通知。

## 驗收矩陣

| 情境 | 預期結果 | 自動測試 |
|---|---|---|
| 標題沒有「獎學金」，但來源契約確定是獎助方案 | live、audit、baseline 都保留公告 | `test_live_preserves_collector_scoped_notice_without_title_keywords`、`test_audit_does_not_modify_repository_or_send_line`、`test_baseline_preserves_notice_without_standard_title_keywords` |
| 同標題、不同年度 | 保留兩筆 | `test_multi_source_keeps_same_named_notice_across_years` |
| 同一公告出現在三個來源 | 一筆公告、兩筆重複來源關聯 | `test_multi_source_preserves_three_source_duplicate_relations` |
| 同一網址截止日改變 | 產生新 revision | `test_revision_hash_changes_when_deadline_changes` |
| 前一天未執行，公告移到第二頁 | 每日增量仍能補抓 | `test_incremental_mode_catches_up_second_page` |
| 嚴格 CSS selector 失效 | 來源失敗關閉 | `test_strict_policy_fails_closed_when_selector_is_missing` |
| 解析 100 列、排除 20 列 | 20 列排除原因完整守恆 | `test_rejection_reason_accounting_explains_every_excluded_row` |
| 初次建立基線 | 不推播歷史公告 | `test_baseline_service_marks_current_items_without_notification_dependencies` |
| 基線後固定頁內容改變 | 重新評估並通知 | `test_baseline_content_change_reopens_and_notifies` |
| 沒有明確符合公告 | LINE 稽核仍列出待人工確認公告 | `test_report_explains_when_no_eligible_items` |

## 成功定義

- `pages_succeeded` 只代表網頁取得成功。
- `raw_rows` 代表方案別名或候選列命中。
- `parsed_rows` 代表成功建立可追蹤公告。
- `child_sources_succeeded` 只計算通過語意驗證的方案。
- `core_covered` 必須在前序核心來源輸出中實際命中方案別名，不會自動視為成功。
- 專用 Collector 已負責來源範圍，服務層不得再用全域標題關鍵字刪除公告。
- 完整稽核中任一方案未通過語意驗證，該方案監測群組在去重前隔離。
