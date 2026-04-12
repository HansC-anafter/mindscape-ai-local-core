# IG UI 重構實作文檔

**文件日期**: 2026-01-19

## 目標

- 將超大型元件拆分為「資料層 / 行為層 / UI 組件」三層，降低耦合與維護成本。
- 統一 API 呼叫與資料解析邏輯，降低重複碼與行為不一致。
- 讓每個檔案可被單人一次讀完（建議 < 300 行）。
- 嚴格控制行為變更，原則上重構期間不新增功能；若因使用體驗/可靠性需要小幅延伸，必須在 TODO 文檔留下稽核紀錄與回歸點。

## 合規與紅線（必讀）

- **架構邊界**：不得因 `mindscape-ai-cloud` 的重構，去變更 `mindscape-ai-local-core` 的架構與邊界規範。
- **禁止繞過 Git / 直接碰 VM**：所有變更必須可追蹤、可回滾。
- **註釋規則**：程式碼註釋必須使用英文；禁用 emoji、禁用非功能性描述。
- **文檔語言**：內部工作文檔一律使用繁體中文；對外文檔一律使用英文。

必讀文件（本次任務需遵守）：

- `mindscape-ai-local-core/docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`
- `mindscape-ai-cloud/docs/architecture/playbook-implementation-guide.md`
- `mindscape-ai-local-core/docs-internal/CAPABILITY_INSTALLATION_GUIDE.md`

## 範圍盤點（ig/ui）

盤點來源：`capabilities/ig/ui/**`（以 `wc -l` 統計；行數為近似尺寸指標）

| 檔案 | 行數 | 重構優先度 | 原因 |
| --- | --- | --- | --- |
| `ui/modules/AccountsPanel.tsx` | 1918 | P0 | 同時負責資料、狀態、UI、互動與多分頁；變更風險最高且回歸成本大 |
| `ui/IGFollowingAnalyzer.tsx` | 954 | P0 | 流程複雜、狀態/串流/polling + API + UI 混在一起 |
| `ui/IGWorkbench.tsx` | 820 | P0 | layout + 模組切換 + 資料載入 + 多視圖混在同檔，耦合高 |
| `ui/modules/MeasurePanel.tsx` | 619 | P1 | 分析邏輯 + UI 混雜；後續擴充成本高 |
| `ui/modules/ReviewPanel.tsx` | 615 | P1 | artifacts 解析 + UI 混雜；資料模型複雜 |
| `ui/modules/PublishPanel.tsx` | 468 | P2 | 可抽出共用表單與 API；對 P0 依賴較低 |
| `ui/modules/EngagePanel.tsx` | 463 | P2 | 類似資料/狀態/顯示混雜；可用同樣拆分模板處理 |
| `ui/modules/ExportPanel.tsx` | 383 | P2 | 對外輸出流程可抽 `api + utils`，UI 仍可維持 |
| `ui/modules/IGDirectCapture.tsx` | 366 | P2 | 可抽出 capture API 與狀態 hook，降低 UI 複雜度 |
| `ui/ReadyScore.tsx` | 353 | P2 | 可拆成計算/視覺組件；避免在其他面板重複使用時擴散 |
| `ui/IGGridViewModal.tsx` | 316 | P2 | modal orchestration 可抽出 hooks/components；尺寸中等可後做 |
| `ui/modules/HashtagPanel.tsx` | 303 | P2 | 封裝資料拉取與 filter，並將列表 UI 拆出 |
| `ui/modules/SeriesPanel.tsx` | 329 | P2 | series mapping/表單狀態可獨立；與 Workbench 模組切換有耦合需小心 |
| `ui/IGTimelineView.tsx` | 224 | P2 | 視圖層可抽 `selectors`；優先度低於 P0/P1 |
| `ui/views/TimelineView.tsx` | 282 | P2 | 視圖層可抽 `selectors`；優先度低於 P0/P1 |
| `ui/views/KanbanView.tsx` | 248 | P2 | 視圖層可抽 `selectors`；優先度低於 P0/P1 |
| `ui/IGPostCard.tsx` | 171 | P2 | UI 組件可拆小，但尺寸不大；可等共用抽象成型後再做 |
| `ui/modules/CreateTemplateDialog.tsx` | 203 | P2 | 對話框流程中等，拆 `api + form` 即可 |
| `ui/IGGridView.tsx` | 78 | P2 | 已小檔，僅在整體抽象成熟後微調 |
| `ui/types.ts` | 43 | P2 | 型別集中處（可能逐步下放到各 feature folder） |

### 盤點引用（供稽核）

- `capabilities/ig/ui/modules/AccountsPanel.tsx:1-296`
- `capabilities/ig/ui/IGFollowingAnalyzer.tsx:1-125`
- `capabilities/ig/ui/IGWorkbench.tsx:1-208`
- `capabilities/ig/ui/modules/MeasurePanel.tsx:1-619`
- `capabilities/ig/ui/modules/ReviewPanel.tsx:1-615`

### P0 現況（截至 2026-01-19）

- `ui/modules/AccountsPanel.tsx`：1918 -> 296
- `ui/IGFollowingAnalyzer.tsx`：954 -> 125
- `ui/IGWorkbench.tsx`：820 -> 208

## 非 UI 範圍（延伸追蹤：ig/tools）

本文件原始範圍是 `capabilities/ig/ui/**`，因此 **tool implementation 檔案不在上一輪 P0/P1 盤點表內**。  
但在 UI 已逐步把「進度/Debug/重跑」等能力做出來後，下一步必須把 tools 層的巨型檔案一起收斂，否則會出現：

- UI/Hook 已模組化，但 backend 工具仍是單一大檔，**診斷/維護成本仍高**
- execution_backend / debug artifacts / rerun endpoint 等新能力會繼續往同一支大檔堆疊

### 盤點（ig/tools）

| 檔案 | 行數 | 建議優先度 | 原因 |
| --- | --- | --- | --- |
| `tools/ig_following_analyzer.py` | 1925 | T0 | Playwright 自動化 + scrolling/anti-detection + artifacts progress + watchdog + account page analyze 全混在同檔，風險與維護成本最高 |

### 建議拆分目標（T0）

保留 `tools/ig_following_analyzer.py` 作為 **registry/tool entrypoint**，其餘實作搬到子模組（避免大範圍 import path 震盪）：

```
capabilities/ig/tools/following_analyzer/
  __init__.py
  tool.py               # IGFollowingAnalyzerTool schema + execute wrapper（可選擇留在舊檔）
  runner.py             # ig_analyze_following() orchestration
  progress.py           # artifacts progress upsert + watchdog
  browser.py            # playwright context / storage_state / anti-detection
  scroll_extract.py     # following dialog scroll + extraction (含 debug screenshots)
  page_analyzer.py      # visit account pages + stats parsing
  utils.py              # classify failure / count parse / risk detect / delays
```

### 執行順序（建議）

1. 先做「純搬移拆檔」：不改邏輯，只把程式碼切到上述模組，並以薄入口檔維持既有載入方式
2. 再做「API/Schema 收斂」：補齊 `execution_backend` 等新參數在 tool schema/metadata 的串接（維持 backward compatible）
3. 最後做「內聚與測試點」：把 watchdog、scroll debug、artifact matching 變成可單元測試的純函式/小類別

## 重構原則

1. **先拆純函式再拆 UI**：先抽出 utils/types/api，再拆 components。
2. **不要改 API 介面**：仍用既有 endpoints，避免後端改動。
3. **每次只抽一層**：避免一次大爆炸改動難以回歸。
4. **UI 行為不變**：只移動程式碼與結構（例外情況需在 TODO 文檔紀錄與回歸點）。
5. **保留入口檔**：現有 import 路徑先保留，減少牽動範圍。

## AccountsPanel 重構計畫（P0）

### 目標結構（建議）

```
ui/modules/accounts/
  AccountsPanel.tsx            # 輕量入口，負責組裝
  types.ts                     # ConnectedAccount/DiscoveredAccount/BrowserSessionStatus
  utils.ts                     # parseCountTextToNumber/formatCount/getProxiedImageUrl
  api.ts                       # fetch.../start.../capture...
  hooks/
    useConnectedAccounts.ts
    useDiscoveredAccounts.ts
    useAccountSnapshots.ts
    useAccountAnalytics.ts
    useBrowserSessionStatus.ts
    useLocalTags.ts
  components/
    AccountsHeader.tsx
    AccountsTabs.tsx
    AccountDetailPanel.tsx
    AccountCardGrid.tsx
    AccountListRow.tsx
    SourcesTab.tsx
    TargetsTab.tsx
    CapturesTab.tsx
    AnalyticsTab.tsx
    SessionTab.tsx
    ImportDialog.tsx
```

補充：目前採用漸進式拆分，入口檔仍保留在 `ui/modules/AccountsPanel.tsx`，其餘拆到 `ui/modules/accounts/`。

### 拆分順序（建議）

1. **抽出 types 與 utils**
   - `ConnectedAccount`, `DiscoveredAccount`, `BrowserSessionStatus`
   - `parseCountTextToNumber`, `formatCount`, `getProxiedImageUrl`
2. **抽出 API**
   - `fetchConnectedAccounts(apiUrl, workspaceId)`
   - `fetchDiscoveredAccounts(apiUrl, workspaceId)`
   - `startFollowingImport(...)`
   - `fetchSnapshots(...)`, `captureSnapshot(...)`
   - `fetchAnalyticsRows(...)`
   - `fetchBrowserSessionStatus(...)`
3. **抽出 hooks**
   - `useConnectedAccounts` 管理 loading/error
   - `useDiscoveredAccounts` 管理 artifacts 解析
   - `useAccountSnapshots` (selected handle → snapshots, compareIds)
   - `useAccountAnalytics` (activeTab === analytics → load)
   - `useBrowserSessionStatus` (profilePath / refresh)
   - `useLocalTags` (localStorage 封裝)
4. **拆 UI 組件**
   - `AccountDetailPanel`：把「已選帳號細節」整段搬出
   - `Tabs`：Sources/Targets/Captures/Analytics/Session 各一檔
   - `TargetsTab` 再拆成 `Grid`/`List` 子組件
   - `SessionTab` 內再拆 `QuickCapturePanel`/`BackendAutomationPanel`
5. **收斂狀態**
   - `AccountsPanel` 僅保留：activeTab、selectedAccount、search/filter
   - 其他狀態下放到各 hook / tab component

### 風險點

- `selectedAccount` 類型分支多，拆出 `AccountDetailPanel` 時需仔細定義 props。
- `loadDiscoveredAccounts` 有合併/去重邏輯，需確保抽到 hook 時不破壞排序與來源累積。
- analytics/tab 與 snapshots 依賴 activeTab，需要避免重構後重複觸發。

## IGFollowingAnalyzer 重構計畫（P0）

### 拆分建議

- `lib/api.ts`：統一 `getApiBaseUrl`（同 IGWorkbench 使用）
- `hooks/useFollowingAnalyzer.ts`
  - 管理 executionId / progress / result / error
  - 封裝 `fetchResultFromArtifacts` 與 polling fallback
- UI 拆分
  - `AnalyzerForm`：輸入區、參數
  - `AnalyzerProgress`：進度顯示
  - `AnalyzerResult`：摘要 + 列表
  - `AnalyzerError`：錯誤顯示

### 重構注意

- 目前 log 訊息密集，建議集中為 `debug` flag（避免污染 console）。
- `useExecutionStream` 行為不要改，只換位置。

## IGWorkbench 重構計畫（P0）

### 拆分建議

- `modules/workbench/` 子資料夾
  - `IGWorkbench.tsx` 僅負責 layout + state 入口
  - `WorkbenchSidebar.tsx`（左邊模組）
  - `WorkbenchContent.tsx`（中間 grid/kanban/timeline 切換）
  - `WorkbenchControlPanel.tsx`（右側執行面板）
  - `moduleRegistry.ts`（模組配置、icon、label、component）
- hooks
  - `useIGPosts`：統一 loadPosts + statusCounts
  - `useRecentRuns`：loadRecentRuns

### 重構注意

- module 切換與 selection state 需要保持原行為
- `getApiBaseUrl` 改成共用函式，避免多處硬編碼

## ReviewPanel / MeasurePanel 重構計畫（P1）

### ReviewPanel

- 把 artifacts 解析抽到 `modules/review/parseReviewArtifacts.ts`（已完成）
- UI 分成 `ReviewList` / `ReviewDetail`
- `ReviewPanel` 只留下：selectedReview + filter

### MeasurePanel

- `useMetrics(post)` 與 `useAnalysis(post)` 各自封裝
- `BackfillDialog` 抽成獨立組件
- 分離 `MetricsCard` / `AnalysisPanel`

## 共用抽象（可逐步導入）

- `lib/api.ts`：統一 baseUrl、fetch wrapper、error normalization
- `lib/artifacts.ts`：專門解析 `artifacts` 到業務模型
- `components/EmptyState`, `components/LoadingState`, `components/StatCard`

## 執行順序（建議）

1. AccountsPanel（types/utils/api/hook）
2. AccountsPanel（UI 組件拆分）
3. IGFollowingAnalyzer（hook + UI）
4. IGWorkbench（拆 panel + module registry）
5. ReviewPanel / MeasurePanel

## 驗證清單

- AccountsPanel
  - Sources / Targets / Captures / Analytics / Session 互動一致
  - Import / Snapshot / Analytics load 行為與原先一致
  - Browser Session 狀態與提示文字一致
- Following Analyzer
  - execution stream + polling fallback 正常
  - result fallback 從 artifacts 取得正常
- Workbench
  - 模組切換、status filter、view mode 切換一致

## 完成定義

- 每個 P0 檔案拆分後主檔 < 300 行
- hooks / components 單一職責
- UI 行為無變更、console 無新增警告
- 若有任何行為延伸，必須在 TODO 文檔留下變更動機、影響面與回歸點
