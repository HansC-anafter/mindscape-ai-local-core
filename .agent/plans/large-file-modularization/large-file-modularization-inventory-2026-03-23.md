# Cloud Repo / Local-Core Repo 大檔模組化盤點

- 產生時間：2026-03-23 Asia/Taipei
- 盤點範圍：`mindscape-ai-cloud`、`mindscape-ai-local-core` 的 `git tracked` 文字檔
- 主清單門檻：`>=1000 行`；接近千行觀察清單：`950-999 行`
- 清理清單：vendor/generated、lockfile、backup/old；這些不建議做模組化拆分

## 單檔計劃目錄

- Wave A：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/README.md`
- Wave B：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/README.md`
- Wave C：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/README.md`
- Wave D：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-d-file-plans/README.md`
- Wave E：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-e-file-plans/README.md`


## 主重構清單（超過千行）（81 檔）

### mindscape-ai-cloud

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/docs/archive/legacy-v1/OPENSEO_IMPLEMENTATION_ROADMAP_20251225.md
- 5959 行，類型：docs
- 重構細則：不要在原檔續寫；改成 `README.md` + `chapters/` 的封存結構，並新增一頁現行版本對照，讓舊內容退出主設計路徑。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/multi_media_studio/YOGA_ACTION_LIBRARY_SCENARIO.md
- 5144 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/implementation/sonic-space-implementation-roadmap-2025-12-27.md
- 4356 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/architecture/api-authentication-architecture-analysis-2025-12-26.md
- 3454 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/kol_vault/docs/KOL_VAULT_IMPLEMENTATION_PLAN.md
- 2839 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/implementation/s1-gcp-vm-deploy-end-to-end-implementation-plan.md
- 2734 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/architecture/todos/video-content-pipeline-pack-capacity-audit-2026-01-20.md
- 2560 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/YOGACOACH_EXTENDED_PLAYBOOKS_ROADMAP.md
- 2483 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/implementation/dispatch-workspace-e2e-verification-plan-2025-12-30.md
- 2382 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/architecture/playbook-implementation-guide.md
- 2308 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/src/components/TeacherVideoUpload.tsx
- 2263 行，類型：code
- 重構細則：拆成 container、presentational components、hooks、types、utils；把資料抓取與渲染細節分離。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/video_chapter_studio/IMPLEMENTATION_ROADMAP.md
- 2126 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/ReferencesPanel.tsx
- 2037 行，類型：code
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/mind-lens/roadmap/phase-b-frontend-ui-review-enhancements.md
- 1838 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/docs/THREAD_VIEW_COMPONENT_SPECIFICATION.md
- 1809 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/frontier_research/docs/INTENT_ADAPTIVE_DESIGN.md
- 1651 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/mind-lens/roadmap/phase-b-frontend-ui-implementation-spec.md
- 1625 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/docs/unsplash-visual-lens-implementation-todos-2025-12-18.md
- 1603 行，類型：docs
- 重構細則：拆成 `README.md`、`themes/`、`checklists/`、`owners.md`、`done-log.md`；把 backlog、決策、驗證紀錄分檔。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/IMPLEMENTATION_PLAN.md
- 1552 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/todos/PHASE0_CRITICAL_GAPS.md
- 1526 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/api/insights_api.py
- 1503 行，類型：code
- 重構細則：先抽型別/常數/錯誤，再拆 pure logic、adapter、side effect；最後補契約測試，確保拆檔不改行為。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/services/divi/docs/phase3/PHASE3_IMPLEMENTATION_PLAN.md
- 1451 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/docs/AI_SEO_COMMON_CONTRACT_2026-01-04.md
- 1447 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/api/web_generation_endpoints.py
- 1442 行，類型：code
- 重構細則：拆成 `router.py`、`schemas.py`、`handlers/`、`service.py`、`permissions.py`；把 request parsing、商業規則、response mapping 分層。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/architecture/site-hub-provider-api-integration-2025-12-26.md
- 1436 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/ReferencesPanel.test.tsx
- 1411 行，類型：test
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx
- 1384 行，類型：code
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/tools/openseo_obsidian_tools.py
- 1370 行，類型：code
- 重構細則：先抽型別/常數/錯誤，再拆 pure logic、adapter、side effect；最後補契約測試，確保拆檔不改行為。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/implementation/architecture-refactoring-2025-12-22/TODOS.md
- 1351 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/kol_vault/docs/KOL_VAULT_CAPABILITY_VISION.md
- 1321 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/brand_identity/api/cis_mapper_endpoints.py
- 1319 行，類型：code
- 重構細則：拆成 `router.py`、`schemas.py`、`handlers/`、`service.py`、`permissions.py`；把 request parsing、商業規則、response mapping 分層。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/VIDEO_UPLOAD_FLOW.md
- 1266 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/implementation/architecture-refactoring-2025-12-22/IMPLEMENTATION_PLAN.md
- 1265 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/docs/IG_WORKBENCH_IMPLEMENTATION_PLAN.md
- 1252 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/multi_media_studio/ui/components/MultiMediaWorkbench.tsx
- 1242 行，類型：code
- 重構細則：拆成 container、presentational components、hooks、types、utils；把資料抓取與渲染細節分離。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/docs/DIVI_SAFEGUARD_IMPLEMENTATION_PLAN.md
- 1235 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/docs/CODE_REFERENCES.md
- 1185 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/sonic_space/docs/PLAYBOOK_IMPLEMENTATION_PLAN.md
- 1175 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/mind-lens/roadmap/full-vision-implementation-roadmap.md
- 1166 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/connectors/wordpress/docs/plugin_admin_menu_architecture.md
- 1157 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/tools/divi_sync_tools.py
- 1156 行，類型：code
- 重構細則：先抽型別/常數/錯誤，再拆 pure logic、adapter、side effect；最後補契約測試，確保拆檔不改行為。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/mind-lens/roadmap/phase-f-saas-implementation-roadmap.md
- 1150 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/tools/following_analyzer/page_visitor.py
- 1133 行，類型：code
- 重構細則：拆成 `schemas.py`、`prompt_builder.py`、`parser.py`、`scorers.py`、`postprocess.py`；把 LLM 呼叫、解析、評分與輸出整形分層。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/mind_lens/store.py
- 1127 行，類型：code
- 重構細則：拆成 `models.py`、`queries.py`、`repository.py`、`mappers.py`、`transactions.py`；避免 SQL/ORM、映射、商業規則混在同檔。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/tools/following_analyzer/runner.py
- 1113 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/services/control_plane_registry.py
- 1090 行，類型：code
- 重構細則：拆成 `models.py`、`loader.py`、`resolver.py`、`cache.py`、`search.py`；把掃描、索引、查詢和快取責任分開。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/docs/IG_CHANNEL_IMPLEMENTATION_PLAN_2026-01-05.md
- 1012 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/followingAnalyzer/hooks/useFollowingAnalyzerExecution.ts
- 1003 行，類型：code
- 重構細則：拆成 `state.ts`、`selectors.ts`、`effects.ts`、`events.ts`；避免單一 hook 同時管理 transport、projection、UI 衍生狀態。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/grant_scout/api/grant_endpoints.py
- 1000 行，類型：code
- 重構細則：拆成 `router.py`、`schemas.py`、`handlers/`、`service.py`、`permissions.py`；把 request parsing、商業規則、response mapping 分層。

### mindscape-ai-local-core

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py
- 2145 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/workflow-orchestrator.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/capability_installer.py
- 1772 行，類型：code
- 重構細則：拆成 `manifest_loader.py`、`validator.py`、`install_executor.py`、`rollback.py`、`reporting.py`；把安裝流程改成可回滾的 step pipeline。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/deprecated-capability-installer.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py
- 1574 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/playbook-run-executor.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_builder.py
- 1542 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/plan-builder.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_registry.py
- 1500 行，類型：code
- 重構細則：拆成 `models.py`、`loader.py`、`resolver.py`、`cache.py`、`search.py`；把掃描、索引、查詢和快取責任分開。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/tool-registry.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/PendingTasksPanel.tsx
- 1450 行，類型：code
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。
- Wave E 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-e-file-plans/pending-tasks-panel.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/artifact_extractor.py
- 1435 行，類型：code
- 重構細則：拆成 `schemas.py`、`detectors.py`、`normalizers.py`、`writers.py`、`telemetry.py`；抽取規則與落盤/副作用分離。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/artifact-extractor.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/artifact_extractor.py
- 1435 行，類型：code
- 重構細則：拆成 `schemas.py`、`detectors.py`、`normalizers.py`、`writers.py`、`telemetry.py`；抽取規則與落盤/副作用分離。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/conversation-artifact-extractor.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/task_manager.py
- 1431 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/task-manager.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/TimelinePanel.tsx
- 1379 行，類型：code
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。
- Wave E 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-e-file-plans/timeline-panel.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_registry.py
- 1374 行，類型：code
- 重構細則：拆成 `models.py`、`loader.py`、`resolver.py`、`cache.py`、`search.py`；把掃描、索引、查詢和快取責任分開。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/playbook-registry.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/wizards/LocalFilesystemManagerContent.tsx
- 1369 行，類型：code
- 重構細則：拆成容器元件、子區塊元件、表單 schema、資料 adapter、事件 handlers；避免單一元件同時承擔流程與 UI 細節。
- Wave E 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-e-file-plans/local-filesystem-manager-content.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/runtime_assets_installer.py
- 1350 行，類型：code
- 重構細則：拆成 `manifest_loader.py`、`validator.py`、`install_executor.py`、`rollback.py`、`reporting.py`；把安裝流程改成可回滾的 step pipeline。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/runtime-assets-installer.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/executions.py
- 1340 行，類型：code
- 重構細則：先抽型別/常數/錯誤，再拆 pure logic、adapter、side effect；最後補契約測試，確保拆檔不改行為。
- Wave D 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-d-file-plans/workspace-executions.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py
- 1331 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/decision-coordinator.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/components/CliApiKeysSection.tsx
- 1269 行，類型：code
- 重構細則：拆成容器元件、子區塊元件、表單 schema、資料 adapter、事件 handlers；避免單一元件同時承擔流程與 UI 細節。
- Wave E 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-e-file-plans/cli-api-keys-section.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py
- 1236 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/playbook-runner.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_installer.py
- 1202 行，類型：code
- 重構細則：拆成 `manifest_loader.py`、`validator.py`、`install_executor.py`、`rollback.py`、`reporting.py`；把安裝流程改成可回滾的 step pipeline。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/playbook-installer.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_embedding_service.py
- 1191 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/tool-embedding-service.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/mindscape/routes.py
- 1181 行，類型：code
- 重構細則：拆成 `router.py`、`schemas.py`、`handlers/`、`service.py`、`permissions.py`；把 request parsing、商業規則、response mapping 分層。
- Wave D 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-d-file-plans/mindscape-routes.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/suggestion_action_handler.py
- 1162 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/suggestion-action-handler.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/panels/ModelsAndQuotaPanel.tsx
- 1159 行，類型：code
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。
- Wave E 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-e-file-plans/models-and-quota-panel.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py
- 1131 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/governance-engine.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_executor.py
- 1127 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/plan-executor.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/intent_analyzer.py
- 1083 行，類型：code
- 重構細則：拆成 `schemas.py`、`prompt_builder.py`、`parser.py`、`scorers.py`、`postprocess.py`；把 LLM 呼叫、解析、評分與輸出整形分層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/intent-analyzer.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/conversation_manager.py
- 1081 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/conversation-manager.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/memory-intent-architecture.md
- 1066 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py
- 1063 行，類型：code
- 重構細則：拆成 `router.py`、`schemas.py`、`handlers/`、`service.py`、`permissions.py`；把 request parsing、商業規則、response mapping 分層。
- Wave D 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-d-file-plans/playbook-execution.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py
- 1061 行，類型：code
- 重構細則：把 prompt 依任務情境拆成多個模板檔，另抽 `variables.py` 與 `render.py`；避免模板字串與 orchestration 邏輯同檔。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/meeting-prompts.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py
- 1042 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/meeting-engine.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tools/workspace_tools.py
- 1024 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave C 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-c-file-plans/workspace-tools.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/context_builder/builder.py
- 1017 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/context-builder.md`

## 接近千行觀察清單（15 檔）

### mindscape-ai-cloud

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/api/references_api.py
- 997 行，類型：code
- 重構細則：先抽型別/常數/錯誤，再拆 pure logic、adapter、side effect；最後補契約測試，確保拆檔不改行為。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/walkto_lab/docs/DEVELOPER_GUIDE_WALKTO_LAB.md
- 997 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/AGENT_CONCEPT_RESEARCH.md
- 991 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/mindscape_cloud_integration/ui/components/MindscapeCloudChannelBindingPanel.tsx
- 985 行，類型：code
- 重構細則：拆成 `...PanelShell.tsx`、`...Toolbar.tsx`、`...List.tsx`、`...Detail.tsx`、`use...State.ts`；把狀態、資料來源、視圖區塊分開。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/docs/unsplash-visual-lens-e2e-verification-2025-12-18.md
- 980 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/docs/multi-lens-composition.md
- 973 行，類型：docs
- 重構細則：至少拆成索引頁、主體章節、範例/附錄三層；避免一個 Markdown 同時承載背景、設計、待辦、驗證。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/YOGACOACH_PLAYBOOK_IMPLEMENTATION_STATUS_2025-12-27.md
- 964 行，類型：docs
- 重構細則：拆成 `README.md`、`themes/`、`checklists/`、`owners.md`、`done-log.md`；把 backlog、決策、驗證紀錄分檔。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/docs/architecture/todos/playbook-alignment-implementation-2025-12-25.md
- 961 行，類型：docs
- 重構細則：拆成 `README.md`、`context.md`、`requirements.md`、`contracts.md`、`flows.md`、`risks.md`、`appendix/`；正文只保留核心設計。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/CHAPTER_SUGGESTION_FIX_PLAN_2026-01-05.md
- 958 行，類型：docs
- 重構細則：拆成 `README.md`、`themes/`、`checklists/`、`owners.md`、`done-log.md`；把 backlog、決策、驗證紀錄分檔。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/openseo/docs/roadmap.md
- 957 行，類型：docs
- 重構細則：拆成 `README.md`、`scope.md`、`architecture.md`、`phases/`、`backlog.md`、`verification.md`；把歷史決策移到 `decisions/`。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/web_generation/divi_sync_cli.py
- 957 行，類型：code
- 重構細則：先抽型別/常數/錯誤，再拆 pure logic、adapter、side effect；最後補契約測試，確保拆檔不改行為。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/docs/YOGACOACH_PRODUCTION_READINESS_FIXES.md
- 951 行，類型：docs
- 重構細則：拆成 `README.md`、`themes/`、`checklists/`、`owners.md`、`done-log.md`；把 backlog、決策、驗證紀錄分檔。

### mindscape-ai-local-core

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/cloud_providers.py
- 999 行，類型：code
- 重構細則：拆成 `router.py`、`schemas.py`、`handlers/`、`service.py`、`permissions.py`；把 request parsing、商業規則、response mapping 分層。
- Wave D 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-d-file-plans/cloud-providers.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/cta_handler.py
- 991 行，類型：code
- 重構細則：先抽 `types.py`、`constants.py`、`errors.py`，再把 pure logic、adapter、side effect handler 分到子模組；原檔只保留協調層。
- Wave B 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-b-file-plans/cta-handler.md`

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py
- 974 行，類型：code
- 重構細則：拆成 `contracts.py`、`state_machine.py`、`planner.py`、`dispatcher.py`、`result_mapper.py`；把流程控制、外部 I/O、結果彙整解耦。
- Wave A 單檔計劃：`/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/dispatch-orchestrator.md`

## 清理／排除清單（33 檔）

### mindscape-ai-cloud

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/umd/react-dom.development.js
- 29924 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/cjs/react-dom.development.js
- 29923 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/csstype/index.d.ts
- 22569 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/.vite/deps/chunk-373CG7ZK.js
- 21626 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/cjs/react-dom-server-legacy.node.development.js
- 7093 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/cjs/react-dom-server.node.development.js
- 7070 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/cjs/react-dom-server-legacy.browser.development.js
- 7029 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/umd/react-dom-server-legacy.browser.development.js
- 7026 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/cjs/react-dom-server.browser.development.js
- 7014 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/umd/react-dom-server.browser.development.js
- 7011 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/@types/react/index.d.ts
- 4587 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/ccapabilities/yogacoach/frontend/react/node_modules/@types/react/ts5.0/index.d.ts
- 4573 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/vite/LICENSE.md
- 3423 行，類型：docs，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react/umd/react.development.js
- 3343 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react/cjs/react.development.js
- 2740 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/electron-to-chromium/full-chromium-versions.js
- 2632 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/.vite/deps/chunk-REFQX4J5.js
- 1908 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/cjs/react-dom-test-utils.development.js
- 1763 行，類型：test，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react-dom/umd/react-dom-test-utils.development.js
- 1759 行，類型：test，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/.package-lock.json
- 1696 行，類型：config，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/electron-to-chromium/full-versions.js
- 1684 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/connectors/wordpress/admin-ui/package-lock.json
- 1671 行，類型：config，標記：lockfile
- 重構細則：不拆檔；先定義 package manager 邊界，只保留必要 lockfile，避免後續把依賴快照誤當成可維護模組。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/package-lock.json
- 1666 行，類型：config，標記：lockfile
- 重構細則：不拆檔；先定義 package manager 邊界，只保留必要 lockfile，避免後續把依賴快照誤當成可維護模組。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/semver/semver.js
- 1643 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/@types/babel__traverse/index.d.ts
- 1506 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/browserslist/index.js
- 1335 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react/cjs/react-jsx-runtime.development.js
- 1333 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/react/cjs/react-jsx-dev-runtime.development.js
- 1315 行，類型：code，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/yogacoach/frontend/react/node_modules/@babel/parser/CHANGELOG.md
- 1073 行，類型：docs，標記：vendor/generated
- 重構細則：不做模組化拆分；先從版本庫移除 vendor/generated 內容，改由安裝或建置流程還原，並補 `.gitignore` 與 bootstrap 說明。

### mindscape-ai-local-core

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/package-lock.json
- 14066 行，類型：config，標記：lockfile
- 重構細則：不拆檔；先定義 package manager 邊界，只保留必要 lockfile，避免後續把依賴快照誤當成可維護模組。

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/pnpm-lock.yaml
- 8410 行，類型：config，標記：lockfile
- 重構細則：不拆檔；先定義 package manager 邊界，只保留必要 lockfile，避免後續把依賴快照誤當成可維護模組。

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/device-node/package-lock.json
- 2680 行，類型：config，標記：lockfile
- 重構細則：不拆檔；先定義 package manager 邊界，只保留必要 lockfile，避免後續把依賴快照誤當成可維護模組。

/Users/shock/Projects_local/workspace/mindscape-ai-local-core/mcp-mindscape-gateway/package-lock.json
- 2021 行，類型：config，標記：lockfile
- 重構細則：不拆檔；先定義 package manager 邊界，只保留必要 lockfile，避免後續把依賴快照誤當成可維護模組。
