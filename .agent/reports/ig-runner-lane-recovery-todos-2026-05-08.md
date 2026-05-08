# IG runner lane recovery todos

最後更新日期：2026-05-08

## 任務邊界

- 範圍限於 IG runner lane、reference running status、batch pin queue / artifact 落地、runner resource failure evidence。
- 不處理任何系統降級，不改能力關閉邏輯，不降低 runner capacity，不把 cloud IG 實作移入 local-core。

## Todo

1. [完成] 監看 `a2793e02-bdcc-413b-baed-359a3c70292b`
   - 上游：`tasks` row、runner-browser log、resource heartbeat。
   - 下游：batch pin artifact、reference rows、analysis follow-up queue。
   - 完成結果：task `succeeded`，result 有 `artifact_id=04c964b2-62ef-459f-85a7-48536d320aeb`、`summary.md`、`result.json`；下一筆 `511ca09d-9735-4249-af88-ad9fe34e71ae` 已接棒 running。

2. [待辦] 補強 batch pin resource failure 診斷
   - 上游：`backend/app/runner/task_executor.py`、`backend/app/runner/resource_pressure.py`、runner heartbeat snapshot。
   - 下游：Deadletter / delayed queue / workbench failure card。
   - 完成條件：失敗原因能區分 resource SIGKILL、timeout、browser lease unavailable、tool-level no candidates，不再只看 exitcode。

3. [完成] 查證並修復 `captured_posts` 模式不必要 browser fallback
   - 上游：`capabilities/ig/tools/ig_batch_pin_tool.py`、`ig_posts`、reference catalog。
   - 下游：batch pin succeeded result、pinned reference analysis enqueue。
   - 完成結果：`source_mode=captured_posts` 仍讀已持久化 `ig_posts` / `ig_accounts_flat.grid_posts_json`，但 pin 階段新增 `allow_browser_fallback=False`、`allow_post_detail_fallback=False`，避免缺圖補救偷佔 browser session；HTTP 下載與 live browser 路徑能力不被移除。

4. [待辦] 修正 sidebar count 語義歧義
   - 上游：`/api/v1/ig/workbench/sidebar-summary` response、WorkbenchExecutionPanel 顯示。
   - 下游：run logs active cards、reference status cards。
   - 完成條件：UI 能清楚區分 reference catalog counts 與 task lane active executions，不再把 `counts.running` 誤解成所有 IG task lanes running。

5. [待辦] 回歸驗證與提交
   - 上游：cloud IG tests、local-core runner tests、pack installer API。
   - 下游：local-core installed IG pack、frontend workbench。
   - 完成條件：測試通過、註釋規則通過、commit 完成；若涉及 IG pack，使用 clean clone `.mindpack` 透過 `localhost:8220` 安裝並驗證。
   - 目前證據：targeted pytest `9 passed`；`git diff --check` 與 `py_compile` 無輸出；尚待 cloud commit、clean clone package、install API 驗證。
