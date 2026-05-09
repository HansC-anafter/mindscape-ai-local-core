# Workspace 載入與 Read API 修復證據報告

最後更新日期：2026-05-10

## 死線原則

- 不調降 runner lane、inflight、任務調度、OCR、LLM、vector、object index、browser profile 或 capability pack 能力。
- 不用 cloud repo 實作語義改寫 local-core 架構邊界。
- 不直接修改 VM/container 內源碼；runtime 驗證只允許透過 repo source、Docker restart、API、DB 查詢與 logs。
- 不使用 `git add -f`、不使用 `--no-verify`。

## 結論

本輪修復已解決兩類明確缺口：

1. UI read endpoint 會被 default executor / DB 慢讀拖住，造成 `/health`、sync status、tasks feed、progress snapshot 互相阻塞。
2. `/api/v1/workspaces/:workspaceId/tasks?limit=50` 在 `include_completed=false` 時先讀出所有 pending / running 再切片；目前 workspace pending 數量已達十幾萬，導致頁面入口直接卡住。

本輪未宣稱完全解決 Next dev 冷編譯。`/workspaces/:workspaceId` 最新 warm 驗證仍為 6.31s，早先冷編譯曾達分鐘級；這是剩餘問題，不是已完成項。

## 證據

### E1. Runtime 容器狀態

> **Evidence**: `docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'`
> ```text
> mindscape-ai-local-core-frontend          Up 16 minutes (healthy)   0.0.0.0:8300->3000/tcp
> mindscape-ai-local-core-backend           Up 4 minutes (healthy)    0.0.0.0:8200->8200/tcp
> mindscape-ai-local-core-postgres          Up 2 days (healthy)       0.0.0.0:5433->5432/tcp
> ```

### E2. 當前仍存在執行負載，不應把所有延遲歸因於單一路由

> **Evidence**: `docker stats --no-stream --format ...`
> ```text
> mindscape-ai-local-core-frontend       137.35%   2.386GiB / 15.6GiB
> mindscape-ai-local-core-runner-browser 141.94%   3.327GiB / 6GiB
> mindscape-ai-local-core-runner-default 259.05%   1.963GiB / 6GiB
> mindscape-ai-local-core-postgres        31.36%   360.7MiB / 15.6GiB
> ```

### E3. 修復前 `/tasks?limit=50` direct backend 也會逾時

> **Evidence**: `curl -m 30 ... http://localhost:8200/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/tasks?limit=50`
> ```text
> curl: (28) Operation timed out after 30009 milliseconds with 0 bytes received
> tasks_backend_direct status=000 total=30.009617 size=0
> ```

### E4. 逾時期間 Postgres active query 指向未受限 pending list

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql ... pg_stat_activity`
> ```text
> local-core-backend | active | IO | DataFileRead | 00:00:44.794309 |
> SELECT * FROM tasks WHERE 1=1 AND workspace_id = 'bac7ce63-e768-454d-96f3-3a00e8e1df69' AND status = 'pending' ORDER BY created_at DESC
> ```

### E5. 修復後 pending query 走新索引

> **Evidence**: `EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM tasks ... status = 'pending' ORDER BY created_at DESC LIMIT 50`
> ```text
> Index Scan using idx_tasks_workspace_status_created_desc on tasks
> Planning Time: 66.548 ms
> Execution Time: 26.597 ms
> ```

### E6. 修復後 `/tasks?limit=50` 不再 30 秒逾時

> **Evidence**: warm runtime curl
> ```text
> tasks_backend_direct_warm2 status=200 total=2.281895 size=193260
> tasks_proxy_warm2 status=200 total=2.102323 size=193260
> ```

### E7. 其他主要 read path 最新驗證

> **Evidence**: runtime curl
> ```text
> backend_health_warm2 status=200 total=0.421184
> cloud_sync_proxy status=200 total=0.091363 size=55
> workspace_health_proxy status=200 total=1.229395 size=1189
> sidebar_proxy_after_taskfix status=200 total=3.052773 size=90295
> root_after_taskfix status=200 total=6.314628 size=9382
> ```

### E8. PostgreSQL 最近 30 分鐘沒有 recovery fatal；只看到人工錯 DB 名稱造成的錯誤

> **Evidence**: `docker logs --since 30m --tail 120 mindscape-ai-local-core-postgres`
> ```text
> 2026-05-09 18:05:47.060 UTC [35378] FATAL:  database "mindscape" does not exist
> ```

### E9. Source 邊界查驗

> **Evidence**: `git diff -- 'web-console/src/app/workspaces/[workspaceId]/page.tsx'`
> ```text
> <no output>
> ```
>
> **Evidence**: `docker exec mindscape-ai-local-core-frontend printenv NEXT_DEV_TURBO`
> ```text
> 0
> ```

## 修復內容與為何不是降級

### 1. Dedicated UI read executor

Source: `backend/app/routes/core/read_executor.py:9-19`

新增 `run_ui_read()`，讓 UI read endpoint 用 bounded executor，不再和其他 default threadpool work 互相飢餓。

為何不是降級：沒有改 runner lane、任務數、任務 admission 或任何 capability；只是隔離 read endpoint 的執行資源，降低 UI read 被長任務卡住的機率。

### 2. Workspace health 走 workspace endpoint 快取，`/healthz` 保持真正 liveness

Source: `backend/app/routes/core/workspace/health.py:21-72`

workspace/system health 仍呼叫 `SystemHealthChecker.check_workspace_health()`，只是加 30 秒短快取與 inflight dedupe。

為何不是降級：`/healthz` 不查 OCR/LLM/vector/object index；完整 workspace health 仍在 `/api/v1/workspaces/:id/health`，沒有移除任何健康檢查能力。

### 3. Cloud sync status 不再為 count 建完整 payload

Source: `backend/app/routes/core/cloud_sync.py:37-84`、`backend/app/services/cloud_sync/offline_changes.py:70-95`

status route 使用 `get_pending_change_count()`，避免為一個 count 排序與保留整批 change payload。

為何不是降級：sync pending changes、pending changes list、summary API 都仍保留；只有 status 的 count 改成 count-only read。

### 4. Workspace tasks 非 completed feed 遵守 `limit`

Source: `backend/app/routes/core/workspace/tasks.py:429-448`

修復前：pending / running 都用 `limit=None` 撈全量，再 `(pending + running)[:limit]`。

修復後：pending 先用 caller `limit`；只有 pending 不足時，running 才讀剩餘數量。

為何不是降級：API 本來就宣告 `limit` 是最大回傳筆數；這次只是讓 DB read 遵守既有 API 合約，不改任務狀態、排程、可見性或執行能力。

### 5. 補 DB 索引支援 workspace/status feed

Source: `backend/alembic_migrations/postgres/versions/20260509164000_add_workspace_execution_feed_indexes.py:17-43`

新增：

- `idx_tasks_workspace_status_created_desc`
- `idx_tasks_workspace_execution_created_desc`
- `idx_artifacts_ws_execution_updated_desc`

為何不是降級：索引只改善查詢路徑，不改資料、不丟資料、不限制工作量。

### 6. Frontend 減少首屏重複/非關鍵 read

Source: `web-console/src/contexts/WorkspaceDataContext.tsx`、`web-console/src/hooks/useWorkspaceData.ts`、`web-console/src/components/WorkspaceChat.tsx`、`web-console/src/lib/sync-api.ts`

已加入短 cache / dedupe、chat path 不在 mount 時強制拉 system health、sync status 前端短 cache。

為何不是降級：手動 refresh 仍會 force；資料來源仍是同一個 backend API；只是避免同一頁面多個 component 重複打同一個 read endpoint。

### 7. Dev proxy 保留 media / IG reference image cache header

Source: `web-console/dev-proxy.mjs:92-120`

只對 media 與 IG reference image 保留 cache header；其他 API 仍 `no-store`。

為何不是降級：不改 image 產生、抓取、分析能力；只是避免已存在的靜態/半靜態圖片每次頁面載入都重新拉。

## 已查驗但不納入本次修復的項目

- root route loader/server page 邊界實驗：目前 `web-console/src/app/workspaces/[workspaceId]/page.tsx` 無 diff，沒有用新入口覆蓋原本 workspace chat。
- Docker `.next` named volume：目前 diff 內沒有 named `.next` volume。
- Turbopack：runtime `NEXT_DEV_TURBO=0`，沒有啟用為預設。早先測試出現 Next package resolution 500，因此不作為本次修復。
- Next dev 冷編譯：仍是未解問題。最新 warm root 為 6.31s；冷啟動分鐘級問題需要另開 import graph / production mode / dev server 編譯策略修復，不能宣稱已完成。

## 驗證結果

> **Evidence**: Python tests
> ```text
> backend/tests/workspace_tasks_route_limits_spec.py ..
> backend/tests/cloud_sync_offline_changes_spec.py ..
> backend/tests/system_health_checker_ollama_spec.py ....
> backend/tests/healthz_liveness_spec.py ...
> 11 passed, 188 warnings in 26.96s
> ```

> **Evidence**: Vitest
> ```text
> src/lib/sync-api.spec.ts (3 tests) 23ms
> Test Files 1 passed (1)
> Tests 3 passed (3)
> ```

> **Evidence**: ESLint
> ```text
> docker exec mindscape-ai-local-core-frontend pnpm exec eslint ...
> <no output, exit 0>
> ```

> **Evidence**: whitespace gate
> ```text
> git diff --check
> <no output, exit 0>
> ```

> **Evidence**: touched code Chinese/emoji check
> ```text
> rg -n "[\p{Han}]|[🆕]" <touched source files>
> <no output, exit 1>
> ```

## 後續待辦

1. 針對 Next dev 冷編譯另開修復：用 bundle/import graph 實證拆解 `/workspaces/[workspaceId]` 的首屏模組重量。
2. 針對 `sidebar-summary` 仍可能 2-5 秒，繼續查 IG summary SQL 與 materialized summary refresh 路徑。
3. 針對 runner 高 CPU 與 Postgres checkpoint / IO 負載，另做 runtime capacity report；不得用調低 inflight 當第一手段。
