# Runtime 頁面載入與 Docker 瓶頸證據報告

最後更新：2026-05-07

## 死線原則

- 不降低 inflight / concurrency / queue partition / resource class。
- 不停用 OCR、LLM、vector、object index、agent dispatch、runner browser 或既有 polling 能力。
- 只修不合理阻塞、錯誤健康檢查語意、重複查詢、同步阻塞 async route、migration fallback 重跑等違反系統邏輯的路徑。

## 範圍

- Frontend：`web-console`、installed IG pack UI、Performance Direction workbench route、IG workbench route。
- Backend API：`/healthz`、`/health`、workspace health、IG workbench APIs、playbook status、execution progress snapshot、capability pack install。
- Runner / Docker：`backend`、`backend-control`、`frontend`、`runner-browser`、`runner-vision`、`postgres`。
- DB：`tasks`、`artifacts`、`ig_batch_pin_account_summary`、`ig_accounts_flat`、`ig_confirmed_targets`、`ig_follow_edges`、`alembic_version`。

## 已查明問題

1. `/healthz` 必須是 liveness，不可查 OCR/LLM/vector/object index。
   證據：`backend/app/main.py` 的 `/healthz` route 註解與 `backend/tests/healthz_liveness_spec.py` 檢查 `SystemHealthChecker`、OCR、LLM、vector、object index 不在 `/healthz` 內。

2. OCR optional 時不可做 DNS/HTTP probe。
   證據：`backend/app/capabilities/core_files/services/ocr_client.py` 在 optional default disabled 時回 `disabled`；`backend/tests/test_ocr_client_optional.py` 與 `backend/tests/system_health_checker_ollama_spec.py` 覆蓋 optional disabled 不 probe。

3. IG workbench 舊 UI 會同一輪打 `sidebar-counts` 與 `active-executions` 兩個 API。
   證據：frontend log 出現連續請求 `/api/v1/ig/workbench/sidebar-counts` 與 `/api/v1/ig/workbench/active-executions`；安裝後 installed file 已含 `/api/v1/ig/workbench/sidebar-summary`，查驗命令 `docker exec mindscape-ai-local-core-frontend grep -n sidebar-summary .../useIGWorkbenchState.ts` 回 `248: ...sidebar-summary...`。

4. `progress-snapshot` 原 route 在 async handler 內做同步 DB / artifact / queue cache 工作。
   證據：`backend/app/routes/core/workspace/tasks.py` 已抽成 `_load_execution_progress_snapshot_payload`，route 改 `return await asyncio.to_thread(...)`；測試 `backend/tests/progress_snapshot_thread_offload_spec.py` 檢查 offload。

5. frontend proxy 曾觀測到進度快照與 IG workbench API 在高壓下 17-29 秒。
   證據：frontend logs 曾記錄 `progress-snapshot` 25.7s/29.4s、`active-executions` 26.9s、`sidebar-counts` 26.6s；修復後後續 logs 出現 `progress-snapshot` 49ms、58ms、92ms、301ms 等樣本，但仍有 `sidebar-counts` 1.9s-4.8s，代表 counts 仍是剩餘熱點。

6. `ig/post-thumbnail` 仍有嚴重長尾。
   證據：frontend logs 記錄 `/api/v1/ig/post-thumbnail/...` 404 但 duration 253s、312s、372s。這不是前端秒開可以容忍的路徑，且不是降低能力能解決，需改為 bounded request + background fetch/cache。

7. runner-browser 是實際資源壓力來源之一。
   證據：`docker stats --no-stream` 顯示 `runner-browser` 約 99%-139% CPU、3.9-4.9GiB / 6GiB；`docker top` 顯示兩個 IG following 子程序與 Chromium renderer 長時間耗 CPU。

8. DB 沒有看到鎖死，但有連線與 transaction 壓力。
   證據：`pg_locks` 僅見 granted `AccessShareLock`；`pg_stat_activity` 曾有 36 idle、1-2 `idle in transaction`，樣本包含 `direction_artifacts`、`system_settings`、pack activation query。

9. installer migration fallback 已修正為只跑 pending revisions。
   證據：pack install response warning 含 `Branch-scoped migration failed for ig, but declared revisions are already applied`，不再重跑全部 23 個 IG revisions；這是避免已套用 migration 被重放，不是跳過 pending migration。

10. IG persistence 已修正 per-row DB writes。
    證據：`capabilities/ig/tools/following_analyzer/persistence.py` 使用 cached engine、`pool_pre_ping=True`、`engine.begin()`、batch `conn.execute(stmt, rows)`；容器檢查顯示 backend 與 runner-browser 都已含 `pool_pre_ping True`、`engine_begin True`、`old_per_row False`。

11. Pack 安裝完成但過程仍會造成高壓。
    證據：IG pack `d1c4e816083f7529afdd03bd5f56b133b33d16f94dcfd124b180552d76711a51` 安裝 API 回 `success:true`、HTTP 200、25.989657s；期間 `backend-control` 約 92% CPU、frontend 約 377% CPU、runner-browser 約 139% CPU、Postgres 約 59% CPU。

12. IG pack 最終已 active。
    證據：`jq '.[] | select(.id=="ig") ...' /private/tmp/capability_packs_20260507.json` 顯示 IG `version:"1.0.4"`、`activation_state:"active"`、`migration_state:"applied"`、`validation.state:"succeeded"`、`failed:0`。

13. PD workbench 仍不是秒開。
    證據：`curl ... /capabilities/performance_direction/start` 先前回 `200,10.692217`，後續仍有 `200,7.614880`。frontend log 同時出現 Next dev compile `10.9s`、`4.7s`，所以 PD workbench 慢包含 dev compile 與 API waterfall。

## 已落地修復

1. `/healthz` liveness 語意驗證。
   為什麼不是降級：workspace/system readiness 沒刪掉，只留在 `/health` 與 workspace health；`/healthz` 不再被 OCR/LLM/vector/object index 拖死。

2. OCR optional disabled 直接回 disabled。
   為什麼不是降級：required mode 仍會檢查 OCR；optional 且未開 profile 時避免對不存在的 `ocr-service` 做 DNS/HTTP probe。

3. IG persistence batch writes + engine reuse。
   為什麼不是降級：保留 accounts、edges、confirmed targets、summary refresh 寫入，只降低 round trips、connection churn 與 stale connection 失敗。

4. Installer pending-only fallback。
   為什麼不是降級：所有真正 pending revisions 仍會執行；只避免已在 applied ancestry 內的 revisions 被重跑。

5. `progress-snapshot` offload。
   為什麼不是降級：回應欄位不縮減，仍回 progress、metadata、queue position、admission state，只把同步 DB/queue work 移出 event loop。

6. IG workbench UI 改用 `sidebar-summary`。
   為什麼不是降級：counts 與 active execution 都保留，只把兩個首屏 API 合併成一個，降低 waterfall 與 DB/API 競爭。

7. `ig/post-thumbnail` 前景請求 bounded fast path。
   為什麼不是降級：cache、DB thumbnail、embed fast path 仍在前景；browser 與 post-detail fallback 沒刪除，改到背景刷新同一份 cache，避免單張縮圖把頁面請求卡 5 分鐘。

## 驗證結果

- local-core：`pytest backend/tests/healthz_liveness_spec.py backend/tests/system_health_checker_readiness_isolation_spec.py backend/tests/test_ocr_client_optional.py backend/tests/system_health_checker_ollama_spec.py backend/tests/runtime_assets_installer_migrations_spec.py backend/tests/progress_snapshot_thread_offload_spec.py -q` -> `13 passed`。
- cloud IG：`pytest capabilities/ig/tests/workbench_api_test.py capabilities/ig/tests/persistence_seed_count_test.py capabilities/ig/tests/ig_seed_summary_fast_path_spec.py -q` -> `20 passed`。
- py_compile：local-core touched modules passed；cloud IG touched modules passed。
- runtime curl：`/api/v1/ig/workbench/sidebar-summary?...` -> `200,1.151090` under live load。
- installed UI：`useIGWorkbenchState.ts` contains `/sidebar-summary` in frontend container。
- pack validation：IG `validation.state=succeeded`、`failed=0`。
- thumbnail pack：cloud commit `5886e72`，pack SHA-256 `5433d10d97c856beecda50d35202596783e7000bce437612aae19471dc06191e`，install API `200,21.617581`，validation succeeded。
- thumbnail runtime：container disk 已含 `allow_slow_fallbacks=False`；control API `8220 /api/v1/ig/post-thumbnail/DVhtY3zD1sU` -> `404,3.173150`，但 backend API `8200` 仍 timeout 8s，因 install response deferred reload：`meeting_sessions=113`。

## 剩餘缺口

1. `ig/post-thumbnail` source/pack 已修，但 `8200` backend process 尚未 reload；在安全窗口 reload 前，frontend 仍可能打到舊 module。
2. `sidebar-counts` 仍有 1.9s-4.8s 樣本，需進一步收斂 count reconciliation。
3. 現有開著的瀏覽器頁籤可能仍跑舊 JS，需使用者刷新後才吃到新 installed UI bundle。
4. PD workbench 仍受 Next dev compile 與多 API waterfall 影響，還不能宣稱秒開。
5. `20260507063000_add_admission_deferred_task_indexes.py` 已存在於 local-core source，但 DB `alembic_version` 未見該 revision；索引已存在，仍需確認是否 stamp/apply，不能盲目動 DB。
6. runner-browser 正在執行 IG browser 任務，不能用 stop/restart 當修復；後續只能做 bounded I/O、cache、DB offload、API 合併。
