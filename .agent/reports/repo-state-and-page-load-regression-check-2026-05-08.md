# Repo 狀態與頁面載入回歸查驗報告

最後更新日期：2026-05-08

## 查驗範圍

- `mindscape-ai-local-core`
- `mindscape-ai-cloud`
- 目標問題：目前全站頁面載入變慢，需用 git 與 runtime 掛載證據判斷是既有壓力、已提交修復、或未提交工作樹變更造成。

## Git 證據

### local-core

- HEAD：`dae0ebe2 fix(runner): keep concurrency locks alive during db stalls`
- 已追蹤未提交檔案：152 個
- 未追蹤檔案：45 個
- `dae0ebe2` 只修改 runner lock / control signal 相關檔案：
  - `backend/app/runner/task_executor.py`
  - `backend/app/runner/worker.py`
  - runner 相關測試
- `f7785d89 Fix runtime liveness and page load bottlenecks` 有修改：
  - `backend/app/main.py`
  - `backend/app/routes/core/workspace/health.py`
  - `backend/app/routes/core/workspace/tasks.py`
  - `backend/app/services/system_health_checker.py`
  - 目標對齊先前要求：`/healthz` liveness 與 workspace/system health 分離、OCR optional 不做不必要 probe。
- 目前未提交工作樹包含會直接影響全站載入的檔案：
  - `web-console/next.config.js`
  - `web-console/src/api/client.ts`
  - `web-console/src/contexts/WorkspaceDataContext.tsx`
  - `web-console/src/lib/sync-api.ts`
  - 未追蹤：`web-console/src/lib/resilient-fetch.ts`
  - 未追蹤：`web-console/src/lib/server-api-proxy.ts`
  - 未追蹤：`web-console/src/app/api/[...path]/route.ts`
  - 未追蹤：`web-console/src/app/health/route.ts`
  - 未追蹤：`web-console/src/app/healthz/route.ts`

### cloud

- HEAD：`53c767d fix(ig): bound batch pin post-detail fallback`
- 已追蹤未提交檔案：46 個
- 未追蹤檔案：7 個
- 近期已提交 IG 修復：
  - `9aa6089 fix(ig): recover captured batch pins from placeholder thumbnails`
  - `dc7cec8 fix(ig): refresh captured batch pin thumbnails`
  - `53c767d fix(ig): bound batch pin post-detail fallback`
- cloud 未提交檔案主要集中在 IG reference UI、PD API / tools / UI / docs；需獨立查驗後才能提交，不可混入 local-core 邊界。

## Runtime 掛載證據

Docker inspect 顯示目前容器直接 bind mount 本機工作樹：

- `mindscape-ai-local-core-frontend`
  - `mindscape-ai-local-core/web-console/src` -> `/app/web-console/src`
  - `mindscape-ai-local-core/web-console/next.config.js` -> `/app/web-console/next.config.js`
- `mindscape-ai-local-core-backend`
  - `mindscape-ai-local-core/backend` -> `/app/backend`
  - `mindscape-ai-local-core/web-console` -> `/app/web-console`
- `mindscape-ai-local-core-runner-browser`
  - `mindscape-ai-local-core/backend` -> `/app/backend`
  - `mindscape-ai-local-core/web-console` -> `/app/web-console`

結論：目前未提交工作樹不是單純待整理狀態，而是會被 runtime 實際讀取。

## 對「原本就這樣」與「改壞」的判斷

目前不能把全站慢載入單純歸因為原本系統行為。git 與 runtime 掛載證據顯示：

- 最近已提交的 `dae0ebe2` 不直接觸碰前端載入或 API proxy。
- 目前工作樹有未提交且已被 runtime 掛載的前端 proxy / shared fetch / workspace data loader 變更，這些檔案有能力影響所有頁面的載入路徑。
- 先前 runtime 證據也顯示 backend、runner-browser、postgres、redis 同時高負載，這是全站慢載入的直接環境壓力。

因此正確結論是：目前慢載入至少包含 runtime 高負載因素；同時，未提交 frontend/backend 工作樹變更是必須優先隔離查驗的回歸風險，不能當作已整理完成。

## 下一步查驗順序

1. 對 `local-core` 未提交變更做功能域分組，先隔離全站載入路徑：
   - proxy：`next.config.js`、`server-api-proxy.ts`、`app/api/[...path]/route.ts`
   - client fetch：`resilient-fetch.ts`、`api/client.ts`、`sync-api.ts`
   - workspace shell：`WorkspaceDataContext.tsx`、`layout.tsx`、`WorkspaceChrome.tsx`
2. 用實測比較：
   - frontend `/healthz`
   - backend `/healthz`
   - `/api/v1/workspaces/?owner_user_id=default-user`
   - `/api/v1/capability-packs/`
   - 目標 workspace / capability 頁首屏載入
3. 只修不合理錯誤：
   - 不降低任務 lane / inflight / 系統能力。
   - 不停用 OCR、LLM、vector、object index、browser。
   - 不把 cloud pack 語義寫入 local-core。
4. 每一個準備提交的變更都必須有：
   - 對應檔案清單
   - 測試命令與結果
   - runtime endpoint 證據
   - 邊界檢查結果
