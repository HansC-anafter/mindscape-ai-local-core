# Frontend Workspace Route Latency Repair Evidence

最後更新日期：2026-05-09

## 範圍

本次只處理 web-console 開啟 workspace root、Performance Direction start、IG workbench host 時的前端 dev route 編譯與載入延遲。未變更 runner lane、task scheduling、OCR、LLM、vector、object index、browser runner、IG 任務語義或 local-core/cloud 邊界。

## 根因證據

- `/healthz` 可在 0.006s 至 0.013s 回應，代表 liveness 本身不是瓶頸。
- `next dev` cold compile 曾在 `/workspaces/[workspaceId]` 進入 8k+ modules，觀測到 201.9s、186.3s、167.6s、137.8s 等長延遲。
- `WorkspacePageClient` 存在不可達的 execution inspector 分支，`selectedExecutionId` 沒有任何 setter 會把它設成非 null，但仍把 execution/governance graph 拉入 root route。
- `WorkspaceRightSidebar` 的 focus execution branch 在 root route 不可達，但仍靜態引用 `ExecutionChatPanel`。
- `WorkspaceModals` 保留 delete、root sandbox、full settings 三組沒有 opener 的 modal graph；實際 sandbox 與 settings 入口位於 OutcomesPanel、sandbox route 與 left sidebar 專屬 modal。
- `dev-proxy` 透過 `pnpm run dev -- ...` 啟動 Next dev，日誌顯示 `next dev -- -H ...`，曾在編譯後出現 `next dev exited code=0`，造成熱狀態被打掉。

## 修復內容

- `web-console/src/app/workspaces/[workspaceId]/WorkspacePageClient.tsx`
  - 移除不可達 `ExecutionInspector` branch，保留原 `/workspaces/:workspaceId` workspace chat 入口。
  - 移除沒有 opener 的 root-level delete、sandbox、full settings modal state。
- `web-console/src/app/workspaces/[workspaceId]/components/WorkspaceRightSidebar.tsx`
  - 移除 root route 不可達的 focus execution branch 與 `ExecutionChatPanel` 靜態依賴。
  - 保留 workspace perspective 的 conversations、AI team、artifact summary、decision panel、mode workbench。
- `web-console/src/app/workspaces/[workspaceId]/components/WorkspaceModals.tsx`
  - 保留 artifact detail 與 thread bundle。
  - 移除沒有 opener 的 root-level delete、sandbox、full settings modal graph。
- `web-console/dev-proxy.mjs`
  - 顯式維持 `/healthz` 為 frontend/Next liveness，不代理 backend health。
  - prewarm 預設仍為空，不會背景搶編譯通道；若明確 opt-in，改成拿到 response headers 後即結束該 prewarm request，避免等待完整 body 卡住。
  - Next dev 啟動改為 `pnpm exec next dev -H ... -p ...`，避免 `pnpm run dev -- ...` 轉參數造成 dev server 生命週期異常。
- `web-console/next.config.js`
  - 加入 `optimizePackageImports: ['lucide-react']`，只改善 icon package import graph，不改 UI 功能。

## 為什麼不是降級

- 移除的 execution inspector、root sandbox/delete/full settings modal 都是 root route 內沒有觸發入口的不可達路徑；對可用入口沒有減少能力。
- Execution detail 仍由既有 `/workspaces/{workspaceId}/executions/{executionId}` route 承接。
- Sandbox preview 仍由 OutcomesPanel 與 `/workspaces/{workspaceId}/sandbox/{sandboxId}` route 承接。
- Runtime、data source settings 仍由 left sidebar 的設定入口承接。
- IG workbench、Performance Direction、workspace chat route 未被替代或搬移。
- 未降低任何 runner concurrency、任務 lane、資源 profile 或 capability pack 能力。

## 驗證結果

- `pnpm exec eslint` 目標檔通過：
  - `dev-proxy.mjs`
  - `dev-proxy.spec.mjs`
  - `next.config.js`
  - `WorkspacePageClient.tsx`
  - `WorkspaceRightSidebar.tsx`
  - `WorkspaceModals.tsx`
- dev-proxy direct assertions 通過：
  - `/healthz` 保持 frontend liveness。
  - `/api/healthz` 不代理 backend。
  - `/api/v1/cloud-sync/status` 仍代理 backend。
  - default prewarm paths 仍為空。
  - Next dev args 改為 `pnpm exec next dev -H 127.0.0.1 -p 3010`。
- HTTP 實測：
  - `/healthz`：200，0.012840s。
  - `/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69`：cold 200，120.843850s；warm after idle 200，2.003927s。
  - `/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/capabilities/performance_direction/start`：cold after root compile 200，22.614338s；warm 200，2.983731s。
  - `/capability-ui-hosts/ig/bac7ce63-e768-454d-96f3-3a00e8e1df69?component=IGWorkbench`：cold after root and PD compile 200，14.833852s；warm 200，3.506681s。
- Docker stats idle 後：
  - frontend CPU 0.00%，memory 2.742GiB / 15.6GiB。
  - backend CPU 0.98%，memory 1.232GiB / 6GiB。
  - postgres CPU 1.91%，memory 286.6MiB / 15.6GiB。

## 未完成缺口

- root route cold compile 仍有 120s 級別，尚未達到秒開；但 warm 已回到 2s 級別。
- workspace root 仍有 8131 modules，表示剩餘主要成本在 workspace chat、left/right sidebar、markdown/chat UI 與 workspace layout shared graph。
- Performance Direction 與 IG host route 仍有 8k+ modules，需後續把 workspace chrome/layout shared graph 從 capability route compile graph 分離，不能用替代頁或降低功能處理。
