# AOL Runtime Workbench 里程碑查驗報告 2026-05-03

## 2026-05-05 PD E2E Preflight Binding

本報告若被引用到 PD storyboard / AOL E2E 驗收，必須同時引用 `pd-storyboard-e2e-preflight-ledger-2026-05-05.md`。Workbench / runtime 里程碑查驗不等於 real IG refs 高品質 storyboard acceptance；正式 PD storyboard E2E 必須先完成 `E2E-PD-PREFLIGHT-000`。

## 1. 查驗範圍

本報告查驗 2026-05-03 這一輪「第一階段大檔拆分後的 Workbench UI i18n 合規與里程碑推進」。查驗範圍限於 `mindscape-ai-local-core` 本地工作站程式與內部文檔，未修改 VM，未修改 `mindscape-ai-cloud` 程式。

## 2. 規範證據

- `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md` 第 11-39 行規定 Local-Core 不得實作 Cloud 業務功能，Local-Core 只提供核心 API 與 runtime substrate。
- `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md` 第 54-115 行規定 local-core 不得直接讀取 cloud 文件系統，不得用環境變數或硬編碼路徑繞過 source/runtime 邊界。
- `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md` 第 1044-1051 行規定絕不允許繞過 Git 直接碰 VM，所有變更必須透過 Git 工作流程。
- `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md` 第 850-855 行規定程式碼註釋使用英文，內部文檔使用繁體中文，禁用實作步驟與紀錄、非功能性描述、emoji。
- `docs-internal/CAPABILITY_INSTALLATION_GUIDE.md` 第 33-39 行規定 capability 不論正式安裝或 smoke deploy 都必須走 `.mindpack` 與 install API，local-core runtime 只讀已安裝 pack 與 runtime alias。
- `mindscape-ai-cloud/docs/architecture/playbook-implementation-guide.md` 第 62-80 行規定 cloud/control plane 與 local-core/semantic-hub execution plane 的責任切分，local-core 是執行面，不是 cloud 體驗控制面。

## 3. 計劃對齊證據

- `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md` 第 234-248 行定義 Work view 必須以 `Focus`、`Guidance`、`Command Ledger`、`Runtime`、`Outcomes`、`Assets`、`Next` 取代 raw graph/debug counters，並把 outliner、ledger、inspector 納入 workbench stage。
- 同一文件第 250-257 行定義 Work view 使用 selected-subgraph canvas，而非固定 debug lane board。
- 同一文件第 259-267 行定義 Work inspector 以任務導向內容呈現 Summary、Guidance、Actions、Context、Runtime、Review。
- 同一文件第 269-275 行定義 Work subgraph 必須呈現 provenance path 與 dense-session caps。
- 同一文件第 277-283 行記錄本輪新增 Workbench i18n keys、三語 locale、translation function prop drilling，以及目前兩個第一階段大檔行數：`AOLMeetingBottomShell.tsx` 498 行、`PropertiesInspector.tsx` 495 行。

## 4. 實作證據

- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx` 第 358-373 行把 `t` 傳入 header toolbar，第 410-432 行把 `t` 傳入 `MeetingWorkbenchStage` 與 inspector rail。
- `web-console/src/components/capabilities/meeting-workbench/MeetingWorkbenchStage.tsx` 第 43-72 行把 `t` 傳入 Object Outliner、Task Canvas 與 Command Ledger Strip，維持三者共用同一 selection/runtime state。
- `web-console/src/components/capabilities/meeting-workbench/MeetingWorkSubgraphCanvas.tsx` 第 10-22 行以 i18n key 定義 Work step，第 84-103 行用 i18n 渲染 selected subgraph 與 provenance path，第 139-177 行用 i18n 渲染 step label、hidden signals 與 awaiting signal。
- `web-console/src/components/capabilities/meeting-workbench/MeetingWorkInspectorPanel.tsx` 第 49-67 行用 i18n 渲染 Summary panel，第 72-107 行用 i18n 渲染 Guidance panel，第 110-128 行用 i18n 渲染 Actions panel，第 132-147 行用 i18n 渲染 Context panel，第 155-167 行用 i18n 渲染 Review fallback。
- `web-console/src/lib/i18n/keys/workbench.ts` 第 82-155 行新增 Workbench shell、canvas、outliner、ledger、provenance、inspector keys。
- `web-console/src/lib/i18n/locales/en/workbench.ts` 第 218-291 行、`web-console/src/lib/i18n/locales/zh-TW/workbench.ts` 第 218-291 行、`web-console/src/lib/i18n/locales/ja/workbench.ts` 第 185-258 行提供對應英文、繁中、日文文案。

## 5. 查驗結果

### 5.1 與當前系統路徑是否一致

結論：一致。

證據：本輪實作只改 `mindscape-ai-local-core` 內的 Workbench frontend、i18n keys/locales 與內部里程碑文檔；沒有新增 cloud business API、沒有新增 capability source direct read、沒有安裝或修改 VM。`git status --short -- <本輪檔案>` 顯示的修改路徑均位於 `web-console/src/...` 或 `docs-internal/...`。

### 5.2 是否能實現設計目標

結論：本輪 product slice 已可支撐原始設計目標的主要前端閉環；真實 pack backend 接入仍需後續按 bounded projection contract 落地。

已達成部分：

- Work view 已從 raw graph viewer 轉成以使用者任務流為中心的 `Focus -> Guidance -> Command -> Runtime -> Outcome -> Next` selected-subgraph canvas。
- Command Ledger、Object Outliner、Inspector slot 目前都掛在同一個 Workbench stage 內，符合「中樞協作平台」要把意圖、物件、runtime proof、資產與下一步放在同一工作殼的方向。
- 新增 UI 文案已接入 i18n keys/locales，符合 UI 正式實作以多國語系英文基底、中文延伸的要求。
- Pack-owned guidance projection contract 已落到 frontend/backend shared contract；IG reference fixture 可投影 PD storyboard target、required context、proposal/review route，PD storyboard fixture 可投影 reels generation guidance 與對應 pack tool selection。
- Command Dock 會在 selected guidance 缺少 required `@` context 時阻擋 Command Ledger 寫入；補齊 PD storyboard mention 後，同一 `/meetings/{meeting_id}/commands` route 才收到包含 source/target 的 command envelope。
- AOL session notification 已由 command-ledger/runtime state 投影，不新增分散 dispatch surface。

尚未完成部分：

- 真實 IG/PD pack backend 尚未接入本輪 fixture 所模擬的完整 guidance/review payload；後續必須由 pack backend 供給，不得在 local-core 寫死 IG/PD 分支。
- review/promote 操作面仍是 review route 可見閉環，尚未做完整審核決策 UI。
- dense session 的 provenance overflow grouping 已落地測試，但仍需要產品視覺 QA 驗證不同 viewport 下的可讀性。

### 5.3 查漏補缺

未發現本輪新增實作違反 cloud/local-core 邊界。主要缺口已從「缺少 pack guidance metadata slot」收斂為「真實 pack backend 何時按 contract 供給資料」。

需要後續補齊：

1. 將 IG/PD 真實 pack graph projection backend 對齊本輪 fixture contract，讓「使用者現在應該做什麼」由 pack backend 投影到 Work view 的 Guidance 與 Next。
2. 把 Command Ledger 與 Review route 做成完整可操作序列：使用者意圖、`@object` 引用、command route、runtime execution、artifact landing、review/promote 都要有同一條可追溯鏈。
3. 增加產品化視覺查驗，確認 Work view 在英文、繁中、日文 locale 下都不因文字長度造成重疊。

## 6. 驗證命令

### 6.1 Meeting Workbench 測試

命令：

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
./node_modules/.bin/vitest run src/components/capabilities/meeting-workbench/*.spec.ts src/components/capabilities/meeting-workbench/*.spec.tsx --config vitest.config.ts
```

結果：

```text
Test Files  16 passed (16)
Tests  57 passed (57)
```

### 6.2 AOL Runtime Shell 相容測試

命令：

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
./node_modules/.bin/vitest run src/components/capabilities/aol-runtime-shell/*.spec.tsx --config vitest.config.ts
```

結果：

```text
Test Files  3 passed (3)
Tests  7 passed (7)
```

### 6.3 Whitespace / diff check

命令：

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
git diff --check
```

結果：

```text
exit code 0
warning: LF will be replaced by CRLF in install.ps1.
warning: LF will be replaced by CRLF in scripts/setup.ps1.
warning: LF will be replaced by CRLF in scripts/start.ps1.
warning: LF will be replaced by CRLF in scripts/start_cli_bridge.ps1.
```

說明：`git diff --check` 通過；上述 CRLF 警告是既有工作樹 line-ending 提示，非本輪 Workbench UI 檔案。

### 6.4 註釋與中文硬編碼查驗

命令：

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
rg -n "TODO|FIXME|XXX|HACK|NOTE:|[一-龥]" web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx web-console/src/components/capabilities/meeting-workbench/SemanticFlowCanvas.tsx web-console/src/components/capabilities/meeting-workbench/MeetingWorkbenchStage.tsx web-console/src/components/capabilities/meeting-workbench/ObjectOutlinerPanel.tsx web-console/src/components/capabilities/meeting-workbench/CommandLedgerStrip.tsx web-console/src/components/capabilities/meeting-workbench/MeetingWorkSubgraphCanvas.tsx web-console/src/components/capabilities/meeting-workbench/MeetingWorkInspectorPanel.tsx web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchTypes.ts web-console/src/lib/i18n/keys/workbench.ts
```

結果：

```text
no matches
```

### 6.5 大檔行數查驗

命令：

```bash
wc -l web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx web-console/src/components/capabilities/meeting-workbench/MeetingWorkSubgraphCanvas.tsx
```

結果：

```text
472 web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx
238 web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx
247 web-console/src/components/capabilities/meeting-workbench/MeetingWorkSubgraphCanvas.tsx
```

### 6.6 前端 type-check

命令：

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
./node_modules/.bin/tsc --noEmit --pretty false --project tsconfig.json
```

結果：

```text
exit code 2
```

說明：type-check 仍因既有 repo-wide 問題失敗，包含 stale `.next` route types、Blender/IG/MMS/video/settings/workspace 等 unrelated 檔案。已修掉本輪範圍內的 type-check 問題；最新輸出不再包含 `web-console/src/components/capabilities/meeting-workbench`、`web-console/src/components/capabilities/aol-runtime-shell`、`PerformanceDirectionWorkbenchHost` 或 `ReferenceGridCard`。

## 7. 最終判定

本輪可以進入收尾驗收：大檔仍壓在 500 行以下，新 Workbench shell 產品 UI 已改為 i18n 基底，meeting central collaboration 的主要 surface 仍然圍繞 object selection、guidance、command ledger、runtime proof、artifact/review、next step 展開。

下一輪應優先把真實 IG/PD pack backend payload 對齊本輪 fixture contract，並補 review/promote 操作面；local-core 端不得新增 pack-specific business branch，只接受 bounded projection、ObjectRef、command template、review route 與 artifact landing。

## 8. Git 可見性注意

命令：

```bash
git check-ignore -v docs-internal/implementation/aol-runtime-workbench-2026-05-02/quality-alignment-report-2026-05-03.md docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md
```

結果：

```text
.gitignore:127:docs-internal/ docs-internal/implementation/aol-runtime-workbench-2026-05-02/quality-alignment-report-2026-05-03.md
.gitignore:127:docs-internal/ docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md
```

說明：內部文檔放置位置符合「不要放到正式對外文檔」要求，但目前 `docs-internal/` 被 `.gitignore` 忽略。若這兩份內部查驗文檔需要進入提交，需要用明確檔案清單與強制加入方式處理，不能使用 `git add .`。
