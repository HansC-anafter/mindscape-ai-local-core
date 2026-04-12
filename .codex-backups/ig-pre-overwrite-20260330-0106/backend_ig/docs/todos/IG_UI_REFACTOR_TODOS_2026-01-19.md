# IG UI 重構任務 TODO（AccountsPanel / IGFollowingAnalyzer / IGWorkbench）

**文件日期**: 2026-01-24  
**範圍**: `mindscape-ai-cloud/capabilities/ig/ui/**`  
**目標**: 依照 `capabilities/ig/docs/IG_UI_REFACTOR_EXECUTION_PLAN.md` 完成 P0 UI 重構，確保行為不變並提升可維護性。

## 合規與紅線（摘要）

- 僅在 `mindscape-ai-cloud` 範圍內重構 UI；不得變更 `mindscape-ai-local-core` 架構與邊界。
- 程式碼註釋一律英文；禁用 emoji、禁用非功能性描述。
- 內部工作文檔使用繁體中文；對外文檔使用英文。

必讀文件（本次任務需遵守）：

- `mindscape-ai-local-core/docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`
- `mindscape-ai-cloud/docs/architecture/playbook-implementation-guide.md`
- `mindscape-ai-local-core/docs-internal/CAPABILITY_INSTALLATION_GUIDE.md`

## 上下游資料範圍（P0）

### AccountsPanel（`capabilities/ig/ui/modules/AccountsPanel.tsx`）

- **入口 props**：
  - `workspaceId: string`
  - `apiUrl: string`
  - `onAccountSelect?: (accountId: string) => void`
- **關聯 UI 組件**：
  - `capabilities/ig/ui/IGFollowingAnalyzer.tsx`
  - `capabilities/ig/ui/modules/IGDirectCapture.tsx`
- **localStorage**：
  - key: `ig:account_tags:${workspaceId}`
- **HTTP 端點（不可改契約）**：
  - `GET /api/v1/media/image?url=...`（fbcdn 圖片 proxy）
  - `GET /api/v1/system-settings/files/browser-profile-status?profile_path=...` 或 `?profile_name=default`
  - `GET /api/v1/site-hub/channels?workspace_id=...&channel_type=instagram`
  - `GET /api/v1/workspaces/{workspaceId}/artifacts?platform=instagram&include_content=true&limit=...`
  - `POST /api/v1/workspaces/{workspaceId}/playbooks/execute`
  - `POST /api/v1/playbooks/execute/start?...`

### IGFollowingAnalyzer（`capabilities/ig/ui/IGFollowingAnalyzer.tsx`）

- **入口 props**：
  - `workspaceId: string`
  - `apiUrl?: string`（fallback 到 `NEXT_PUBLIC_LOCAL_CORE_API_URL` / localhost）
  - `defaultUserDataDir?: string`
- **關聯 hook（行為不可變）**：
  - `useExecutionStream(executionId, workspaceId, baseApiUrl, onEvent)`
- **HTTP 端點（不可改契約）**：
  - `GET /api/v1/playbooks/execute/{executionId}/result`（polling fallback）
  - `GET /api/v1/workspaces/{workspaceId}/artifacts?playbook_code=ig_analyze_following&limit=...&include_content=true`
  - `GET /api/v1/artifacts/{artifactId}`（補抓單筆 artifact）
  - `POST /api/v1/playbooks/execute/start?playbook_code=ig_analyze_following&profile_id=default-user&workspace_id=...&auto_execute=true`

### IGWorkbench（`capabilities/ig/ui/IGWorkbench.tsx`）

- **入口 props**：
  - `workspaceId: string`
  - `apiUrl?: string`（fallback 到 `NEXT_PUBLIC_LOCAL_CORE_API_URL` / localhost）
- **HTTP 端點（不可改契約）**：
  - `GET /api/v1/workspaces/{workspaceId}/artifacts?platform=instagram&include_content=true&limit=...`
  - `GET /api/v1/workspaces/{workspaceId}/executions?limit=...&playbook_code_prefix=ig_`
  - `POST /api/v1/playbooks/execute`
- **模組依賴（需維持匯入/行為）**：
  - `modules/SeriesPanel.tsx`, `modules/HashtagPanel.tsx`, `modules/ReviewPanel.tsx`, `modules/ExportPanel.tsx`
  - `modules/PublishPanel.tsx`, `modules/MeasurePanel.tsx`, `modules/EngagePanel.tsx`, `modules/AccountsPanel.tsx`
  - `IGGridView.tsx`, `views/KanbanView.tsx`, `views/TimelineView.tsx`, `ReadyScore.tsx`

## TODO（實作細項）

### P0-1 AccountsPanel 拆分（優先）

- **目標結構**（保留舊入口檔作為 re-export，避免擴散改動）：
  - 新增：`capabilities/ig/ui/modules/accounts/`（feature folder）
  - 保留：`capabilities/ig/ui/modules/AccountsPanel.tsx`（薄 wrapper / re-export）
- **拆分順序**（只搬移與封裝，避免行為變更）：
  - [ ] `types.ts`：`ConnectedAccount` / `DiscoveredAccount` / `BrowserSessionStatus`
  - [ ] `utils.ts`：`parseCountTextToNumber` / `formatCount` / `getProxiedImageUrl`
  - [ ] `api.ts`：封裝 AccountsPanel 使用到的 fetch（統一 headers、錯誤處理）
  - [ ] `hooks/*`：封裝資料載入與 localStorage（loading/error/state 下放）
  - [ ] `components/*`：先抽「可搬移的大段 UI」，再逐步細拆
  - [ ] `AccountsPanel.tsx`：收斂 state，只保留跨 tab 的最小狀態
- **高風險點（需先建立回歸清單）**：
  - `selectedAccount` 為 union type，props boundary 需要明確，避免 UI 分支遺漏
  - artifacts 合併/去重/排序邏輯抽到 hook 後，需確保結果穩定
  - `activeTab` 觸發的 lazy-load（snapshots/analytics）需避免重複觸發或漏觸發
  - Browser session status 的 profilePath fallback 與 UI 文案需維持一致

### P0-2 IGFollowingAnalyzer 拆分

- [ ] 抽出 `lib/api.ts` 或 `lib/getApiBaseUrl.ts`（避免多處 hardcode）
- [ ] 抽出 `hooks/useFollowingAnalyzer.ts`（executionId/progress/result/error、polling、artifacts fallback）
- [ ] UI 拆分為 `components/AnalyzerForm`、`AnalyzerProgress`、`AnalyzerResult`、`AnalyzerError`
- [ ] 保持 `useExecutionStream` 行為與事件分支完全一致（僅移動程式碼）

### P0-3 IGWorkbench 拆分

- [ ] 建立 `ui/modules/workbench/`（或 `ui/workbench/`）做 feature folder
- [ ] 拆分 panels：`WorkbenchSidebar` / `WorkbenchContent` / `WorkbenchControlPanel`
- [ ] 抽出 `moduleRegistry.ts`（icon/label/component mapping）
- [ ] 抽出 hooks：`useIGPosts`（含 artifacts → IGPost mapping）、`useRecentRuns`
- [ ] 維持 module 切換、selection state、viewMode/statusFilter 行為與 props 傳遞

## 驗證清單（最低門檻）

- AccountsPanel
  - Sources / Targets / Captures / Analytics / Session：互動與顯示一致
  - Import、Snapshot、Analytics load：行為一致（含 loading/error 狀態）
  - Browser Session status：狀態偵測與提示文字一致
- IGFollowingAnalyzer
  - execution stream 正常，polling fallback 正常
  - artifacts fallback 正常（能從 `/api/v1/workspaces/{workspaceId}/artifacts` 找到結果）
- IGWorkbench
  - 模組切換、status filter、view mode 切換一致
  - artifacts → posts mapping 結果一致（含多 content items 的展開規則）

## 完成定義（Definition of Done）

- P0 三個入口檔（AccountsPanel / IGFollowingAnalyzer / IGWorkbench）各自主檔 < 300 行（薄入口可例外，但不得再承載業務邏輯）
- hooks/components 單一職責，資料載入與 UI 顯示分離
- API 呼叫端點與 payload 契約不變
- 無新增敏感資訊、無中文程式碼註釋、無 emoji

## 變更摘要（更新時必填）

> 每次原子更新若涉及程式碼實作，需在此附上：**路徑、摘要、行數範圍**（例：`path/to/file.tsx:12-88`）。

| 日期 | 範圍 | 摘要 | 檔案與行數 |
| --- | --- | --- | --- |
| 2026-01-24 | ui | Targets 篩選先套用完整已載入清單，再做可視分頁；seed/source 選單改用完整清單計數 | `capabilities/ig/ui/modules/accounts/hooks/useDiscoveredAccounts.ts:7-143`, `capabilities/ig/ui/modules/AccountsPanel.tsx:71-439` |
| 2026-01-24 | ui | IGWorkbench Run Logs 改為分頁掃描 artifacts 並改抓 detail（降低刷新時內容拉取成本，避免 timeout） | `capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel.tsx:125, 280-423` |
| 2026-01-24 | tools/migrations | 新增 ig_accounts_flat migration 與分析落地寫入 | `capabilities/ig/migrations.yaml:1-12`, `capabilities/ig/migrations/versions/20260124170000_create_ig_accounts_flat_table.py:1-73`, `capabilities/ig/tools/following_analyzer/runner.py:32-158, 241-268, 1559-1575` |
| 2026-01-19 | docs | 建立本任務 TODO 文檔（P0 上下游資料範圍與驗證門檻） | `capabilities/ig/docs/todos/IG_UI_REFACTOR_TODOS_2026-01-19.md:1-130` |
| 2026-01-19 | ui | AccountsPanel 抽離 `types/utils` 到 feature folder，主檔改為引用新模組（行為不變） | `capabilities/ig/ui/modules/AccountsPanel.tsx:13-25`, `capabilities/ig/ui/modules/accounts/types.ts:1-55`, `capabilities/ig/ui/modules/accounts/utils.ts:1-48` |
| 2026-01-19 | ui | AccountsPanel 抽離第一批 API（browser profile status、site-hub channels）到 `accounts/api.ts`，主檔改走封裝函式（行為不變） | `capabilities/ig/ui/modules/accounts/api.ts:1-31`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-25, 83-111, 206-236` |
| 2026-01-19 | ui | AccountsPanel 抽離 artifacts / execute API 到 `accounts/api.ts`，主檔改用封裝（行為不變） | `capabilities/ig/ui/modules/accounts/api.ts:1-71`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-21, 240-258, 366-406, 462-499, 500-544, 546-567` |
| 2026-01-19 | ui | AccountsPanel 抽離 localStorage tags 到 `useLocalAccountTags`（行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useLocalAccountTags.ts:1-47`, `capabilities/ig/ui/modules/AccountsPanel.tsx:65, 147-183` |
| 2026-01-19 | ui | AccountsPanel 抽離 browser session status 到 `useBrowserSessionStatus`（行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useBrowserSessionStatus.ts:1-105`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-23, 65-74` |
| 2026-01-19 | ui | AccountsPanel 抽離 connected accounts（site-hub channels）到 `useConnectedAccounts`（行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useConnectedAccounts.ts:1-62`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-24, 37-42, 74-82, 294-306` |
| 2026-01-19 | ui | AccountsPanel 抽離 discovered accounts 的 artifacts 解析與合併規則到純函式（含 `target_seed`） | `capabilities/ig/ui/modules/accounts/discoveredAccounts.ts:1-118`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-24, 81-113` |
| 2026-01-19 | ui | AccountsPanel 抽離 discovered accounts 的 fetch/state 到 `useDiscoveredAccounts`（保留 `loadDiscoveredAccounts()` 介面，行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useDiscoveredAccounts.ts:1-33`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-24, 37-45, 76-96` |
| 2026-01-19 | ui | AccountsPanel 抽離 filter selectors（search/source/seed/targets）到純函式（行為不變） | `capabilities/ig/ui/modules/accounts/selectors.ts:1-84`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-24, 130-160` |
| 2026-01-19 | ui | AccountsPanel 抽離 targets filters UI 到 `TargetsFilters` component（行為不變） | `capabilities/ig/ui/modules/accounts/components/TargetsFilters.tsx:1-70`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-26, 957-971` |
| 2026-01-19 | ui | AccountsPanel 抽離 sources tab cards（Known sources/seeds/connected accounts）為 components（行為不變） | `capabilities/ig/ui/modules/accounts/components/KnownSourcesCard.tsx:1-46`, `capabilities/ig/ui/modules/accounts/components/KnownSeedsCard.tsx:1-46`, `capabilities/ig/ui/modules/accounts/components/ConnectedAccountsCard.tsx:1-42`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-29, 1008-1085` |
| 2026-01-19 | ui | AccountsPanel 抽離 captures tab cards（following list / account snapshot）為 components（行為不變） | `capabilities/ig/ui/modules/accounts/components/CaptureFollowingListCard.tsx:1-32`, `capabilities/ig/ui/modules/accounts/components/CaptureAccountSnapshotCard.tsx:1-48`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-31, 1042-1073` |
| 2026-01-19 | ui | AccountsPanel 更新 source/seed options 的 count 計算為 unique handle 去重（行為調整：更符合「targets 數」語意） | `capabilities/ig/ui/modules/accounts/selectors.ts:32-85` |
| 2026-01-19 | ui | AccountsPanel 抽離 analytics tab 為 `AccountsAnalyticsPanel` component（行為不變） | `capabilities/ig/ui/modules/accounts/components/AccountsAnalyticsPanel.tsx:1-206`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-32, 1098-1132` |
| 2026-01-19 | ui | AccountsPanel 抽離 targets grid/list view 為 components（行為不變） | `capabilities/ig/ui/modules/accounts/components/TargetsGrid.tsx:1-97`, `capabilities/ig/ui/modules/accounts/components/TargetsList.tsx:1-60`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-34, 1088-1134` |
| 2026-01-19 | ui | AccountsPanel 抽離 Import dialog 為 `ImportAccountsDialog` component（行為不變） | `capabilities/ig/ui/modules/accounts/components/ImportAccountsDialog.tsx:1-61`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-35, 1101-1123` |
| 2026-01-19 | ui | AccountsPanel 抽離 account detail view 為 `AccountDetailPanel` component（行為不變） | `capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx:1-428`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-36, 305-336` |
| 2026-01-19 | ui | AccountsPanel 抽離 session tab 為 `SessionTab` component（行為不變） | `capabilities/ig/ui/modules/accounts/components/SessionTab.tsx:1-226`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-37, 433-458` |
| 2026-01-19 | ui | AccountsPanel header 合併 tabs + actions，並收斂主要間距（版面更緊湊，行為不變） | `capabilities/ig/ui/modules/accounts/components/AccountsTabs.tsx:1-64`, `capabilities/ig/ui/modules/accounts/components/AccountsHeaderActions.tsx:1-71`, `capabilities/ig/ui/modules/accounts/components/SessionTab.tsx:43-70`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-39, 325-364, 463-513` |
| 2026-01-19 | ui | DiscoveredAccount sources 型別擴充（schema/seed version；行為不變） | `capabilities/ig/ui/modules/accounts/types.ts:26-35` |
| 2026-01-19 | ui | 全域合規清理：移除 emoji/符號標記（含勾叉/箭頭/警告符號等）以符合註釋規範（行為不變） | `capabilities/ig/ui/modules/accounts/components/SessionTab.tsx:1-226`, `capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx:1-428`, `capabilities/ig/ui/modules/accounts/components/TargetsGrid.tsx:1-97`, `capabilities/ig/ui/modules/accounts/components/TargetsList.tsx:1-60`, `capabilities/ig/ui/IGFollowingAnalyzer.tsx:1-968`, `capabilities/ig/ui/modules/MeasurePanel.tsx:1-619`, `capabilities/ig/ui/modules/ExportPanel.tsx:1-383`, `capabilities/ig/ui/modules/ReviewPanel.tsx:1-615`, `capabilities/ig/ui/modules/SeriesPanel.tsx:1-329`, `capabilities/ig/ui/modules/EngagePanel.tsx:1-463`, `capabilities/ig/ui/views/TimelineView.tsx:1-282`, `capabilities/ig/ui/modules/IGDirectCapture.tsx:1-366` |
| 2026-01-19 | ui | SessionTab 修正 `IGDirectCapture` import path（行為不變） | `capabilities/ig/ui/modules/accounts/components/SessionTab.tsx:13-15` |
| 2026-01-19 | ui | discovered accounts 合併規則更新：加入 schema/seed version、以 captured_at 決定覆蓋、sources 去重（行為調整：更新資料更可靠） | `capabilities/ig/ui/modules/accounts/discoveredAccounts.ts:1-170` |
| 2026-01-19 | ui | AccountsPanel 抽離 snapshots（載入/compare/capture）到 `useAccountSnapshots`（行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useAccountSnapshots.ts:1-131`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-25, 58-112, 174-204` |
| 2026-01-19 | ui | AccountsPanel 抽離 analytics artifacts 載入到 `useAccountsAnalytics`（行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useAccountsAnalytics.ts:1-96`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-26, 56-95, 166-170` |
| 2026-01-19 | ui | AccountsPanel 抽離 import handles handler 到 `useImportHandles`（行為不變） | `capabilities/ig/ui/modules/accounts/hooks/useImportHandles.ts:1-70`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-27, 100-141` |
| 2026-01-19 | ui | AccountsPanel 抽離 sources/captures/targets 的 tab content wrapper（主檔更薄；行為不變） | `capabilities/ig/ui/modules/accounts/components/SourcesTab.tsx:1-45`, `capabilities/ig/ui/modules/accounts/components/CapturesTab.tsx:1-43`, `capabilities/ig/ui/modules/accounts/components/TargetsTab.tsx:1-49`, `capabilities/ig/ui/modules/AccountsPanel.tsx:18-39, 216-287` |
| 2026-01-19 | ui | AccountsPanel 抽離 overlays（Import dialog / Following analyzer）並移除非必要 imports，主檔降到 < 300 行（行為不變） | `capabilities/ig/ui/modules/accounts/components/AccountsOverlays.tsx:1-57`, `capabilities/ig/ui/modules/AccountsPanel.tsx:1-295` |
| 2026-01-19 | ui | AccountsPanel 新增 run status bar（分析/快照執行狀態提示；行為延伸） | `capabilities/ig/ui/modules/accounts/hooks/useAccountsRunStatus.ts:1-148`, `capabilities/ig/ui/modules/accounts/components/AccountsRunStatusBar.tsx:1-78`, `capabilities/ig/ui/modules/AccountsPanel.tsx:23-24, 132-168` |
| 2026-01-19 | ui | AccountDetailPanel 回復 Back button 的左側箭頭（改用 icon；行為不變） | `capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx:1-55` |
| 2026-01-19 | ui | IGFollowingAnalyzer 抽離 types + execution hook（stream/polling/artifacts fallback；行為不變） | `capabilities/ig/ui/followingAnalyzer/types.ts:1-50`, `capabilities/ig/ui/followingAnalyzer/hooks/useFollowingAnalyzerExecution.ts:1-518`, `capabilities/ig/ui/IGFollowingAnalyzer.tsx:1-317` |
| 2026-01-19 | ui | IGFollowingAnalyzer 拆 UI sections 為 components（Form/Progress/Results），主檔降到 < 300 行（行為不變） | `capabilities/ig/ui/followingAnalyzer/components/AnalyzerForm.tsx:1-131`, `capabilities/ig/ui/followingAnalyzer/components/AnalyzerProgressView.tsx:1-54`, `capabilities/ig/ui/followingAnalyzer/components/AnalyzerResultsView.tsx:1-93`, `capabilities/ig/ui/IGFollowingAnalyzer.tsx:1-125` |
| 2026-01-19 | ui | IGWorkbench 抽離 types/module registry/state hook + sidebar/header/execution panel components，主檔降到 < 300 行（行為不變） | `capabilities/ig/ui/workbench/types.ts:1-27`, `capabilities/ig/ui/workbench/moduleRegistry.ts:1-33`, `capabilities/ig/ui/workbench/hooks/useIGWorkbenchState.ts:1-322`, `capabilities/ig/ui/workbench/components/WorkbenchSidebar.tsx:1-59`, `capabilities/ig/ui/workbench/components/WorkbenchHeader.tsx:1-118`, `capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel.tsx:1-227`, `capabilities/ig/ui/IGWorkbench.tsx:1-249` |
| 2026-01-19 | ui | discovered accounts 解析補上 `ig_account_snapshot` 來源（profile/sources 合併；行為調整：資料更完整） | `capabilities/ig/ui/modules/accounts/discoveredAccounts.ts:177-277` |
| 2026-01-19 | ui | AccountsRunStatusBar 支援 `onOpen` CTA，並在 AccountsPanel run status 為 analyzer 提供快速開啟（行為延伸） | `capabilities/ig/ui/modules/accounts/components/AccountsRunStatusBar.tsx:27-103`, `capabilities/ig/ui/modules/AccountsPanel.tsx:140-166` |
| 2026-01-19 | ui | AccountsPanel 進一步壓縮排版與空行，主檔維持 < 300 行（行為不變） | `capabilities/ig/ui/modules/AccountsPanel.tsx:1-296` |
| 2026-01-19 | ui | IGWorkbench 清理未使用 imports/非必要頂部描述註釋（行為不變） | `capabilities/ig/ui/IGWorkbench.tsx:1-20` |
| 2026-01-19 | ui | TimelineView 日期分組改用本地日期 key，避免 `toISOString()` 時區導致跨日分組錯誤（行為修正） | `capabilities/ig/ui/views/TimelineView.tsx:103-114, 142-149, 218-221` |
| 2026-01-19 | ui | ReviewPanel 抽離 artifacts -> review model 解析為純函式並改用共用 artifacts API（行為不變） | `capabilities/ig/ui/modules/review/types.ts:1-36`, `capabilities/ig/ui/modules/review/parseReviewArtifacts.ts:1-45`, `capabilities/ig/ui/modules/ReviewPanel.tsx:1-121` |
| 2026-01-19 | ui | MeasurePanel 抽離 metrics/analysis 型別、效能標記色彩 utils、metrics/analyze hooks（行為不變） | `capabilities/ig/ui/modules/measure/types.ts:1-25`, `capabilities/ig/ui/modules/measure/utils.ts:1-26`, `capabilities/ig/ui/modules/measure/hooks/useMeasureMetrics.ts:1-31`, `capabilities/ig/ui/modules/measure/hooks/useMeasureAnalysis.ts:1-62`, `capabilities/ig/ui/modules/MeasurePanel.tsx:1-155` |
| 2026-01-19 | ui | ReviewPanel 拆分 UI 為 List/Detail components，主檔降到 < 300 行（行為不變） | `capabilities/ig/ui/modules/review/components/ReviewListView.tsx:1-119`, `capabilities/ig/ui/modules/review/components/ReviewDetailView.tsx:1-244`, `capabilities/ig/ui/modules/ReviewPanel.tsx:1-215` |
| 2026-01-19 | ui | MeasurePanel 拆分 UI 為 components（header/metrics/analysis/advanced/backfill dialog），主檔降到 < 300 行（行為不變） | `capabilities/ig/ui/modules/measure/components/MeasureHeader.tsx:1-28`, `capabilities/ig/ui/modules/measure/components/MetricsCards.tsx:1-99`, `capabilities/ig/ui/modules/measure/components/MeasureAnalysisPanel.tsx:1-90`, `capabilities/ig/ui/modules/measure/components/AdvancedFeaturesPanel.tsx:1-42`, `capabilities/ig/ui/modules/measure/components/BackfillDialog.tsx:1-115`, `capabilities/ig/ui/modules/MeasurePanel.tsx:1-243` |
| 2026-01-19 | ui | P1 面板收斂 playbook execute 呼叫到共用 `executeWorkspacePlaybook`，並新增 `modules/api.ts` 作為共用入口（行為不變） | `capabilities/ig/ui/modules/api.ts:1-1`, `capabilities/ig/ui/modules/ReviewPanel.tsx:1-198`, `capabilities/ig/ui/modules/MeasurePanel.tsx:1-228`, `capabilities/ig/ui/modules/measure/hooks/useMeasureAnalysis.ts:1-55` |
| 2026-01-19 | docs | 補上 tools 層（`ig_following_analyzer.py`）延伸追蹤與拆分建議（T0） | `capabilities/ig/docs/IG_UI_REFACTOR_EXECUTION_PLAN.md:66-120` |
| 2026-01-19 | tools | ig_following_analyzer 拆分為 `following_analyzer/` 子模組並保留薄入口檔（registry import path 不變；行為不變） | `capabilities/ig/tools/ig_following_analyzer.py:1-39`, `capabilities/ig/tools/following_analyzer/utils.py:1-139`, `capabilities/ig/tools/following_analyzer/progress.py:1-21`, `capabilities/ig/tools/following_analyzer/page_analyzer.py:1-133`, `capabilities/ig/tools/following_analyzer/scroll_extract.py:1-743`, `capabilities/ig/tools/following_analyzer/runner.py:1-787`, `capabilities/ig/tools/following_analyzer/tool.py:1-103`, `capabilities/ig/tools/following_analyzer/__init__.py:1-15` |
