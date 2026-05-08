# IG runner lane recovery evidence report

最後更新日期：2026-05-08

## 死線原則

- 不調降 local-core 或 IG pack 的系統調度能力；不得以降低 inflight、關閉 OCR/LLM/MLX/browser/vector/object index 作為修復手段。
- IG 業務邏輯只允許落在 `mindscape-ai-cloud/capabilities/ig`；local-core 只作為已安裝 pack 的 runtime host。
- 不繞過 Git 直接修改 VM、container runtime 檔案或資料庫資料；runtime 只做讀取、查證、安裝與服務重啟驗證。
- capability 正式落地必須使用已提交且 clean 的 source clone 打 `.mindpack`，並透過 `localhost:8220` control plane install API 安裝。
- 不使用 `git add -f`，不繞過 hook，不把被忽略的內部草稿當作正式提交內容。

## 上下游資料範圍

- 上游：IG workbench UI、`/api/v1/ig/workbench/sidebar-summary`、`/api/v1/ig/references`、`tasks`、`runner_heartbeats`、`runner_locks`、IG pack migrations。
- 中游：local-core runner browser / vision / default containers、Redis runner queue、admission deferred release、runner task executor retry / deadletter path。
- 下游：reference catalog cards、run logs sidebar、batch pin artifacts、pinned reference analysis queue、following analysis seed state。

## 目前已驗證狀態

1. IG pack installed state：`curl http://localhost:8200/api/v1/capability-packs/ | jq '.[] | select(.id=="ig")'` 回傳 `activation_state=active`、`migration_state=applied`、validation `succeeded`、`failed=0`、`warnings=0`。
2. RUNNING reference catalog：`/api/v1/ig/references/?analysis_status=RUNNING&include_counts=false` 回傳 `total=1`、`returned=1`，且該筆為 live task `93da1c65-0894-451e-a0f7-a52ddcee56f5`。
3. 三條 IG lane 目前 live running：
   - `ig_analyze_following`: `495616fe-9877-4c1d-a69c-58c83509fbcb`
   - `ig_analyze_pinned_reference`: `93da1c65-0894-451e-a0f7-a52ddcee56f5`
   - `ig_batch_pin_references`: `a2793e02-bdcc-413b-baed-359a3c70292b`，後續已完成並由 `511ca09d-9735-4249-af88-ad9fe34e71ae` 接棒 running。
4. Batch pin 已有落地資產證據：
   - `c39fc993-7508-419e-acfa-cc5aaf450267` 狀態 `succeeded`，result 含 `artifact_id=b7fcc7bd-9334-4f64-8428-42d4d690b850`、`summary.md` 與 `result.json` 路徑。
   - `a2793e02-bdcc-413b-baed-359a3c70292b` 狀態 `succeeded`，result 含 `artifact_id=04c964b2-62ef-459f-85a7-48536d320aeb`、`summary.md` 與 `result.json` 路徑，完成時間 `2026-05-08T06:16:22.021040+00:00`。
5. Browser runner resource state：`docker stats` 顯示 runner-browser 仍存活；`runner_heartbeats` 顯示 `browser_local` inflight 1，最新 resource snapshot 有 cooldown/admission deferred 訊號。
6. 已確認 `runner_locks` 沒有殘留 IG/browser/profile lock rows；目前 pending 的 batch pin 主要被 `admission_deferred` 或合法 concurrency lock 阻擋。
7. `tasks` 表 schema 真相是 `pack_id` 承載 IG playbook code；本輪查詢已改用 `mindscape_core.tasks.pack_id in ('ig_analyze_following','ig_analyze_pinned_reference','ig_batch_pin_references')`，避免把不存在的 `playbook_code` 欄位當真源。
8. `runner_heartbeats` 真實欄位是 `runner_id`、`profile_code`、`inflight`、`heartbeat_at`、`resource_snapshot`；本輪未再使用不存在的 `status`、`inflight_count` 欄位判讀。

## 已落地修復

- `65d6b19 Fix IG reference running status paging`
  - RUNNING reference filter 改用 live task truth，避免 stale catalog RUNNING rows 讓 UI 顯示多筆假的 active。
  - 狀態 total 改走 workspace counts table，避免大型 catalog COUNT 掃描。
- `efbb980 Register IG status sort migration`
  - 補上 migration registry，避免 migration drift warning。
- `9403ae2 Add IG status validated paging index`
  - 新增 status + `validated_at NULLS LAST` paging index，直接 SQL 從約 4.5s 降到約 15.8ms。
- `319ccc12 Align runner resource failure snapshots`
  - local-core runner 對 SIGKILL / resource failure 記錄 resource snapshot，避免只有 exitcode 而缺少資源證據。
- 本輪 cloud IG source 修復：captured-posts batch pin 不再把缺圖補救升級為 browser/post-detail fallback。
  - 插入點：`capabilities/ig/tools/ig_pin_reference.py` 轉傳既有 `fetch_thumbnail_bytes(...)` fallback flags；`capabilities/ig/tools/ig_batch_pin_tool.py` 在 `source_mode=captured_posts` 時傳入 `allow_browser_fallback=False`、`allow_post_detail_fallback=False`。
  - 不是系統降級：live browser batch pin、手動 pin、post thumbnail proxy 的慢速 fallback 能力仍保留；只約束「已持久化資料來源」不得額外偷佔 browser session。
  - 測試證據：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest capabilities/ig/tests/ig_batch_pin_tool_test.py capabilities/ig/tests/ig_pin_reference_thumbnail_fallback_test.py capabilities/ig/tests/post_thumbnail_proxy_test.py capabilities/ig/tests/thumbnail_post_detail_resource_test.py`，結果 `9 passed in 0.57s`。
  - 靜態證據：`git diff --check` 針對 4 個 target 檔案無輸出；`py_compile` 針對 `ig_pin_reference.py`、`ig_batch_pin_tool.py`、`thumbnail_fetcher.py` 無輸出。

## 未結案缺口

1. Batch pin 仍有零星 `exitcode=-9`。目前證據顯示 task executor 將 `subprocess_sigkill` 記錄進 `execution_context.resource_pressure_source`，並保留 resource snapshot；本輪已降低 captured-posts 路徑額外 browser fallback 的資源競爭，但仍需繼續觀察是否還有 Docker/cgroup OOM、browser renderer、或 subprocess lifecycle 造成的 SIGKILL。
2. Browser runner cooldown 日誌在 cooldown 期間會顯示 `reasons=[]`，但 resource snapshot 內保留過去觸發原因；日誌本身可讀性不足，會干擾排查。
3. Sidebar `counts.running` 仍是 reference catalog running count，不等於三條 task lane running count；active_executions 才是 lane truth。這不是資料庫雙真源，但 UI 命名仍容易誤判。
4. `playbook_executions` 表有舊的 running rows，不可作為任務真源；目前任務真源是 `tasks` 與 workbench sidebar API。

## 下一步驗證

1. 將本輪 cloud IG 修復提交，使用 clean clone 打 `ig.mindpack`，透過 `localhost:8220` control plane install API 安裝。
2. 安裝後驗證新 batch-pin captured-posts 任務仍能落地資產，且 runner-browser 不再出現該路徑觸發的 thumbnail browser/post-detail fallback。
3. 查 runner cooldown 日誌是否能在不降低調度能力的前提下保留 cooldown origin，使排查不再依賴 DB JSON。
4. 針對 sidebar count 語義補 UI/API 報告與修復計劃，區分 reference catalog counts 與 task lane active executions。
