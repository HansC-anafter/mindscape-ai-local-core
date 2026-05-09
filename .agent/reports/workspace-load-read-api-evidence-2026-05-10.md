# Workspace 載入與 Read API 修復證據報告

最後更新日期：2026-05-10

## 死線原則

- 不調降 runner lane、inflight、任務調度、OCR、LLM、vector、object index、browser profile 或 capability pack 能力。
- 不用 cloud repo 實作語義改寫 local-core 架構邊界。
- 不直接修改 VM/container 內源碼；runtime 驗證只允許透過 repo source、Docker restart、API、DB 查詢與 logs。
- 不使用 `git add -f`、不使用 `--no-verify`。

## 結論

本輪修復已解決三類明確缺口：

1. UI read endpoint 會被 default executor / DB 慢讀拖住，造成 `/health`、sync status、tasks feed、progress snapshot 互相阻塞。
2. `/api/v1/workspaces/:workspaceId/tasks?limit=50` 在 `include_completed=false` 時先讀出所有 pending / running 再切片；目前 workspace pending 數量已達十幾萬，導致頁面入口直接卡住。
3. request-time capability API activation 在 middleware 內同步 import/register router，第一個 IG API request 會阻塞整個 backend event loop，連 `/healthz` 都可能 30 秒無回應。

本輪未宣稱完全解決 Next dev 冷編譯或 root client graph 重量。最新驗證顯示 `/workspaces/:workspaceId` hot path 已可回到約 1 秒，但 frontend 重啟後 cold compile 仍會落在 70 秒等級；這是剩餘待修項，不是已完成項。

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

### E8. PostgreSQL 曾出現 recovery fatal，不能再宣稱沒有 recovery

> **Evidence**: first post-commit runtime curl 與 Postgres log
> ```text
> FATAL: the database system is not yet accepting connections
> DETAIL: Consistent recovery state has not been yet reached.
> 2026-05-09 18:20:17.133 UTC [1] LOG:  database system is ready to accept connections
> ```
>
> **Evidence**: recovery 後查驗
> ```text
> pg_is_in_recovery = f
> ```

### E9. Request-time capability activation 修復前會阻塞 liveness

> **Evidence**: 修復前重啟後 curl
> ```text
> backend_health_retry status=000 total=30.006434
> tasks_proxy_retry status=000 total=30.006738
> ```
>
> **Evidence**: backend log 同期間仍在 request-time activation / capability loading
> ```text
> Loaded API router from ig/api/avatar_proxy.py
> Registered capability API router for ig with prefix: /api/v1/ig
> Loaded capability: ig (38 tools)
> ```

### E10. Request-time capability activation 修復後不再拖死 `/healthz`

> **Evidence**: 修復後重啟，IG activation 同時 healthz 持續 200
> ```text
> Request-time capability activation completed for ig in 2151ms
> GET /healthz HTTP/1.1" 200 OK
> after_restart_healthz_2 status=200 total=0.017286
> healthz_post_activation status=200 total=0.019578
> ```
>
> **Evidence**: 修復後主要 API runtime curl
> ```text
> tasks_proxy_post_activation status=200 total=0.688464
> references_proxy_post_activation status=200 total=1.219273
> ig_sidebar_repeat1 status=200 total=0.165088
> ig_active_executions status=200 total=0.349243
> ig_sidebar_counts_endpoint status=200 total=1.749660
> workspace_root_warm2 status=200 total=4.025387
> workspace_health_warm2 status=200 total=1.618280
> cloud_sync_warm2 status=200 total=1.940110
> ```

### E11. Source 邊界查驗

> **Evidence**: `git status --short`
> ```text
> 只列出 mindscape-ai-local-core 內 web-console 與 .agent/reports 變更。
> 未列出 mindscape-ai-cloud 檔案。
> ```
>
> **Evidence**: `rg "mindscape-ai-cloud|playbook-implementation-guide" web-console/src web-console/dev-proxy.mjs`
> ```text
> <no output>
> ```

### E12. Root workspace 入口已恢復原 workspace chat，不再用 capability menu 覆蓋

> **Evidence**: `web-console/src/app/workspaces/[workspaceId]/page.tsx`
> ```text
> return <WorkspacePageClientLoader workspaceId={workspaceId} />;
> ```
>
> **Evidence**: `web-console/src/app/workspaces/[workspaceId]/WorkspaceRootClient.tsx`
> ```text
> <Header />
> <UpdateBanner clientVersion="1.0.0" />
> <WorkspaceRuntimeFrame workspaceId={workspaceId}>
>   <WorkspacePageClient workspaceId={workspaceId} />
> </WorkspaceRuntimeFrame>
> ```
>
> **Evidence**: Safari hard reload 後視覺查驗
> ```text
> /workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69 顯示 Mindscape AI 工作站、專案列表、workspace chat textarea、New Conversation。
> 未顯示「多平台內容一鍵生成」capability menu 作為 root page。
> ```

### E13. 最新 root path 量測：hot 已改善，cold 仍未達標

> **Evidence**: `curl -sS -m 180 ... /workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69`
> ```text
> workspace_root_visible_gated_cold status=200 total=91.486833 size=8622
> workspace_root_visible_gated_hot status=200 total=1.073608 size=8622
> ```
>
> **Evidence**: `docker logs --tail 80 mindscape-ai-local-core-frontend`
> ```text
> ✓ Compiled /workspaces/[workspaceId] in 70.2s (1783 modules)
> request {"path":"/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69","upstream":"next_dev","duration_ms":91477.93}
> ```

### E14. 最新 runtime 負載仍會影響 cold compile，不可把 slow page 全部歸因於單一 UI route

> **Evidence**: `docker stats --no-stream mindscape-ai-local-core-frontend ...`
> ```text
> mindscape-ai-local-core-frontend          169.31%   1.027GiB / 15.6GiB
> mindscape-ai-local-core-runner-browser     32.54%   2.094GiB / 6GiB
> mindscape-ai-local-core-runner-default    174.25%   2.714GiB / 6GiB
> mindscape-ai-local-core-postgres           43.06%   328.3MiB / 15.6GiB
> ```

### E15. 前端仍觀測到可見 IG workbench / refs / execution polling 競爭 backend read path

> **Evidence**: `docker logs --tail 80 mindscape-ai-local-core-frontend`
> ```text
> /api/v1/ig/workbench/sidebar-summary duration_ms=4465.6
> /api/v1/ig/references/ duration_ms=5742.99
> /api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/agents duration_ms=4159.74
> /api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/health duration_ms=13762.8
> /api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/executions/4f493881-5e9e-463c-848f-cb7c89881674/progress-snapshot duration_ms=4873.55
> ```

### E16. 背景頁籤 gating 與同 GET 合併插入點

> **Evidence**: `web-console/src/lib/page-visibility.ts:1-18`
> ```text
> isDocumentHidden() 以 document.visibilityState 判定 hidden。
> onDocumentVisible() 只在 visibilityState 變回 visible 時執行 callback。
> ```
>
> **Evidence**: `web-console/src/components/workspace/WorkspaceChatRuntimeControls.tsx:66-101`
> ```text
> hidden 時不 fetch agents；visible resume 再 fetch；agents GET 使用 sharedGetFetch dedupKey workspace-agents。
> ```
>
> **Evidence**: `web-console/src/app/capabilities/ig/components/workbench/hooks/useIGWorkbenchState.ts:234-330`
> ```text
> hidden 時不 fetch recent runs / targets total；visible IG workbench 原 refresh path 保留；sidebar-summary 與 targets-total 使用 sharedGetFetch。
> ```
>
> **Evidence**: `web-console/src/app/capabilities/ig/components/modules/referencesPanel/useReferencesScrollSync.ts:87-191`
> ```text
> hidden 時不做 references background refresh / head sync；visible resume 會 reset 或 sync head。
> ```

### E17. ProjectCard 非展開/hidden 不再搶首屏 card detail read

> **Evidence**: `web-console/src/app/workspaces/[workspaceId]/components/ProjectCard.tsx:203-264`
> ```text
> !isExpanded 或 document hidden 時不打 /projects/:id/card；
> visible resume 透過 visibilityLoadTick 重新觸發；
> card detail GET 使用 sharedGetFetch dedupKey workspace-project-card。
> ```

### E18. 最新自動化查驗

> **Evidence**: `git diff --check`
> ```text
> <no output, exit 0>
> ```
>
> **Evidence**: `./node_modules/.bin/vitest run dev-proxy.spec.mjs`
> ```text
> dev-proxy.spec.mjs (11 tests)
> Test Files 1 passed
> Tests 11 passed
> ```
>
> **Evidence**: `./node_modules/.bin/vitest run src/components/workspace/WorkspaceChatRuntimeControls.spec.tsx src/lib/resilient-fetch.spec.ts`
> ```text
> WorkspaceChatRuntimeControls.spec.tsx (1 test)
> resilient-fetch.spec.ts (4 tests)
> Test Files 2 passed
> Tests 5 passed
> ```
>
> **Evidence**: `npm run type-check`
> ```text
> tsc --noEmit exited with code 2.
> Errors were in existing unrelated capability/type debt including blender_bridge, character_training, multi_media_studio, video_chapter_studio, settings, pendingTasks, and meeting-workbench files.
> No TypeScript error in the files changed by this visibility/read-path iteration was listed.
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

### 8. Request-time capability activation 移出 backend event loop

Source: `backend/app/app_bootstrap/capability_activation_middleware.py:46-67`

修復前：seed-only activation 在 middleware 內同步呼叫 `activate_capability_api_code()`，第一個 IG API request 會在 event loop 內 import/register 多個 router。

修復後：同一個 `activate_capability_api_code()` 仍完整執行，但透過 `asyncio.to_thread()` 等待結果，讓 backend event loop 可繼續處理 `/healthz` 與其他 read request。

為何不是降級：沒有少載 capability、沒有跳過 router registration、沒有改 pack enablement、沒有改 scheduler 或 runner；只改 activation 執行位置，保留同一套能力與同一個 activation 成功/失敗紀錄。

### 9. Workspace root 恢復原 chat entry，能力入口不再覆蓋 root

Source: `web-console/src/app/workspaces/[workspaceId]/page.tsx`、`web-console/src/app/workspaces/[workspaceId]/WorkspaceRootClient.tsx`

root page 只載入 workspace chat runtime frame，不再以 capability launcher menu 取代既有 workspace chat。capability 路由仍保留在 `/workspaces/:workspaceId/capabilities/...`。

為何不是降級：沒有移除 capability、沒有移除 workbench；只是恢復原 URL 的既有 UX 邊界，capability 仍從 capability URL 進入。

### 10. 背景頁籤/非展開 UI read gating

Source: `web-console/src/lib/page-visibility.ts`、`web-console/src/components/workspace/WorkspaceChatRuntimeControls.tsx`、`web-console/src/app/capabilities/ig/components/workbench/hooks/useIGWorkbenchState.ts`、`web-console/src/app/capabilities/ig/components/modules/referencesPanel/useReferencesFetchLifecycle.ts`、`web-console/src/app/capabilities/ig/components/modules/referencesPanel/useReferencesScrollSync.ts`、`web-console/src/app/workspaces/[workspaceId]/components/ProjectCard.tsx`

hidden document 不再主動發送 agents、IG sidebar-summary、references refresh/head sync、workspace auxiliary health/tasks/executions、project card detail 等 read request；頁籤變回 visible 時會 resume refresh。

為何不是降級：visible 頁面和使用者操作的資料刷新能力保留；任務執行、scheduler、runner lane、IG pack 能力完全不變。這是把不可見 UI 的讀取競爭移出 critical path，不是減少系統能力。

### 11. 相同 GET 的前端合併

Source: `web-console/src/lib/resilient-fetch.ts` 既有 `sharedGetFetch()`、本輪接到 agents、executor route、workspace data、IG sidebar-summary、references、project card detail。

為何不是降級：資料仍來自同一 API；只合併同一時間相同 GET 的 in-flight request，避免同頁多 component 重複打同一個 read endpoint。

## 已查驗但不納入本次修復的項目

- root route loader/server page 邊界實驗：目前 `web-console/src/app/workspaces/[workspaceId]/page.tsx` 無 diff，沒有用新入口覆蓋原本 workspace chat。
- Docker `.next` named volume：目前 diff 內沒有 named `.next` volume。
- Turbopack：runtime `NEXT_DEV_TURBO=0`，沒有啟用為預設。早先測試出現 Next package resolution 500，因此不作為本次修復。
- Next dev / root client graph：仍是未解問題。最新 hot root 為 1.07s，但 frontend restart 後 cold root 仍為 91.49s，proxy log 顯示 `/workspaces/:workspaceId` upstream 是 `next_dev` 且 cold compile 70.2s / 1783 modules。需要另開 import graph / dev server 編譯策略修復，不能宣稱已完成。

## 驗證結果

> **Evidence**: Python tests
> ```text
> backend/tests/capability_activation_middleware_spec.py . 1 passed
>
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

1. 針對 Next dev / root client graph 另開修復：用 bundle/import graph 實證拆解 `/workspaces/[workspaceId]` 的首屏模組重量。
2. 針對 `sidebar-summary` 冷 counts 仍約 1.7-1.9 秒，繼續查 IG summary SQL 與 materialized summary refresh 路徑。
3. 針對 runner 高 CPU 與 Postgres checkpoint / IO 負載，另做 runtime capacity report；不得用調低 inflight 當第一手段。
