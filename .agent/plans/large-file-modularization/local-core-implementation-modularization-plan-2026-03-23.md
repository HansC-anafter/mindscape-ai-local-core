# Local-Core Implementation Modularization Plan

Source inventory: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/large-file-modularization-inventory-2026-03-23.md`

Scope:
- Category: `mindscape-ai-local-core` implementation files only
- Files covered: 34 code files
- Thresholds inherited from the inventory: 31 files `>=1000` lines, 3 files `950-999` lines
- Goal: split orchestration, conversation, routing, installer/registry, and workspace/settings UI into stable modules without changing runtime behavior

---

## Phase 1: Evidence Collection

### Evidence Items

- E1. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:1-80` declares workflow execution, template resolution, tool execution, and cloud connector access in one module; `WorkflowOrchestrator` starts at line 62 and the file still defines `_classify_error` at line 2129 in a 2145-line file.
- E2. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_builder.py:1-90` mixes planning, capability registry access, external backend loading, model selection, and tracing; `PlanBuilder` starts at line 34 and the last helper sits at line 1472 in a 1542-line file.
- E3. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:1-110` mixes API router setup, schema imports, lifecycle hooks, file serving, dispatch helpers, and start-execution transport logic; the file begins its route surface at line 35 and still exposes `get_global_executions` near line 961.
- E4. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/task_manager.py:20-80` imports `backend.app.services.artifact_extractor.ArtifactExtractor` at line 32 and instantiates it at line 79, so the conversation task path already depends on the root extractor rather than the conversation copy.
- E5. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/artifact_extractor.py:1-80` defines another `ArtifactExtractor` class starting at line 27, but a full-project grep found no imports of `services.conversation.artifact_extractor` or `conversation.artifact_extractor`.
- E6. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/__init__.py:1-13` explicitly labels `capability_installer.py` as the old unified installer and names modular replacements; `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_installer.py:1-23` says it was extracted from `capability_installer.py`.
- E7. A full-project grep over `backend/` and `scripts/` found no runtime callers for `CapabilityInstaller(` or `services.deprecated.capability_installer`, so `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/capability_installer.py` is structurally dead for runtime code even though docs still mention it.
- E8. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/PendingTasksPanel.tsx:1-260` contains an inline subtitle subcomponent, inline animation CSS, domain types, fetch/update handlers, task filtering, and the main panel export in one 1450-line client component; the primary export starts at line 211.
- E9. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/TimelinePanel.tsx:123-141` exports a single `TimelinePanel` component in a 1379-line file, and current imports mount it from `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx:9`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/playbooks/DefaultLeftSidebar.tsx:5`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/components/WorkspaceLeftSidebar.tsx:7`.
- E10. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/panels/ModelsAndQuotaPanel.tsx:10` imports `CliApiKeysSection`, and the same panel renders that section again near line 853 while both files are themselves 1000+ line components.
- E11. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/wizards/LocalFilesystemManagerContent.tsx:149-160` exports a single large content component that is mounted from both `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/wizards/LocalFilesystemManager.tsx:4` and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/StoragePathConfigModal.tsx:5`.
- E12. Structural symbol sampling across the 34 files shows concentration rather than thin-module design: `tool_registry.py` has 33 top-level definitions across 1500 lines, `workspace_tools.py` has 36 across 1024 lines, `backend/features/mindscape/routes.py` has 40 across 1181 lines, and `backend/features/workspace/executions.py` has 24 across 1340 lines.
- E13. The inventory report covers 34 local-core implementation files in this category, with backend service/orchestration files dominating the list and five `web-console` UI components forming the frontend hotspot cluster.

### Phase 1.5: Historical Regression Analysis (Git History)

- H1. `workflow_orchestrator.py` recently absorbed execution chat, registry completion tracking, ordering fixes, and service-layer stabilization in commits `42d1799`, `f7131ce`, `a2af848`, and `b98ee2d`. The pattern is additive growth, not boundary reduction.
- H2. `plan_builder.py` was touched by `6671c7f`, `3683884`, `56d0caa`, and `9b91069`, spanning capability infra, fail-loud dispatch, async DB work, and PostgreSQL adaptation. The file keeps becoming the default insertion point for unrelated planning concerns.
- H3. `playbook_run_executor.py` was expanded by execution chat, meeting dispatch, multimodal restore, and error handling commits (`42d1799`, `442386e`, `643e19f`, `a2af848`), which is consistent with execution-path accretion.
- H4. `playbook_execution.py` saw pack activation, callback bridge, unified governance dispatch, and queue-position work (`04cdf83`, `442386e`, `643e19f`, `f4a302d`), confirming that transport and orchestration changes are landing in the same route file.
- H5. `PendingTasksPanel.tsx` and `TimelinePanel.tsx` both show repeated UI expansions (`b264811`, `98b7a9f`, `c3921d7`, `1d34970`, `42d1799`, `f8ae209`) rather than extraction into reusable hooks or section components.

Conclusion from history:
- The current failure mode is not one bad refactor; it is repeated feature accretion into already-large files.
- The new plan must structurally prevent future growth by forcing package-level seams, compatibility facades, and explicit ownership boundaries.

---

## Phase 2: Problem Definition + Severity Scoring

1. **Execution orchestration concentration**: workflow execution, governance, runner dispatch, meeting turns, and execution transport are spread across multiple 1000+ line files with overlapping responsibilities, so every execution change has wide blast radius (E1, E3, E12, H1, H3, H4).
2. **Conversation pipeline split-brain**: planning, task lifecycle, CTA/suggestion handling, context building, and artifact extraction are fragmented across large files, and artifact extraction currently exists in two different locations with only one canonical caller path (E2, E4, E5, E12, H2).
3. **Installer/registry lifecycle ambiguity**: deprecated unified installer code still lives in-tree, while registry, installer, runner, embedding, and workspace tools remain oversized and partially extracted, so the architecture does not clearly distinguish active modules from archived ones (E6, E7, E12).
4. **Route boundary leakage**: route modules and feature endpoints still mix HTTP contracts, provider creation, file serving, dispatch decisions, and backend orchestration, which blocks independent refactors and focused API tests (E3, E12, H4).
5. **Frontend workspace/settings monoliths**: large client components mix fetch logic, event wiring, filtering rules, inline utilities, and rendering, which makes UI changes hard to test and forces duplication across pages, sidebars, and settings surfaces (E8, E9, E10, E11, H5).

### FMEA-lite Priority Table

| Problem | Severity | Detection | Priority |
|---|---:|---:|---:|
| P1 Execution orchestration concentration | 5 | 4 | 20 |
| P2 Conversation pipeline split-brain | 5 | 4 | 20 |
| P3 Installer/registry lifecycle ambiguity | 4 | 4 | 16 |
| P4 Route boundary leakage | 4 | 3 | 12 |
| P5 Frontend workspace/settings monoliths | 3 | 4 | 12 |

---

## Phase 3: Assumption Verification (CoVe)

| Assumption | Verification | Result |
|---|---|---|
| `deprecated/capability_installer.py` is not an active runtime dependency | Full-project grep for `CapabilityInstaller(` and deprecated import paths in `backend/` and `scripts/` | No runtime callers found; treat as archive/removal candidate, not a refactor target |
| `conversation/artifact_extractor.py` is not the canonical extractor | Full-project grep for `conversation.artifact_extractor` import paths, plus `task_manager.py` import inspection | No callers found; `task_manager.py` imports the root `backend.app.services.artifact_extractor.ArtifactExtractor` |
| Large frontend files are still mounted in the current UI | Grep import sites for `PendingTasksPanel`, `TimelinePanel`, `CliApiKeysSection`, `LocalFilesystemManagerContent`, `ModelsAndQuotaPanel` | All five are active and mounted from current workspace/settings shells |
| Modular installer extraction already started | Inspect `deprecated/__init__.py` and `playbook_installer.py` headers | Verified; legacy unified installer should be finished into archive/removal rather than expanded |
| Existing tests/scripts can protect this refactor | Inspect `web-console/package.json`, `backend/tests/`, and the existing inventory of execution/playbook/tool tests | Verified; backend pytest files and frontend `lint`, `type-check`, and `vitest` tooling exist |

---

## Phase 3.5: Pre-Mortem

1. **Import cycle regression**: extracting shared contracts from execution and conversation code can create circular imports between orchestrators, stores, and routes.
   - Mitigation: create shared `contracts.py`, `errors.py`, and `clock.py` modules first; keep temporary compatibility facades at old import paths until callers are migrated.
2. **Dead-code deletion regression**: removing `deprecated/capability_installer.py` or `conversation/artifact_extractor.py` too early can break docs, scripts, or hidden imports.
   - Mitigation: add a short-lived compatibility shim or explicit archival notice first, run full-project grep again after migration, then delete in a final cleanup commit.
3. **Frontend hydration/state regression**: splitting large client components can accidentally move `use client` boundaries, break context assumptions, or duplicate fetch subscriptions.
   - Mitigation: keep a thin client shell at the original file path for one migration step, extract hooks and pure presentational sections underneath it, and run type-check/lint plus focused UI tests before path moves.

---

## Phase 4: Plan Writing

### Step 0: Backup and Safety Baseline

Resolves Problem #1, Problem #2, Problem #3, Problem #4, Problem #5

Before any code changes that may touch task, execution, or artifact flows, create a database backup:

```bash
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
```

Then establish the refactor skeleton before moving behavior:
- Add new package directories with `__init__.py` or `index.ts` boundaries first.
- Convert each legacy large file into a compatibility facade only after its first extraction lands.
- Do not delete old paths until all callers, tests, and docs are migrated.

### Wave 1: Execution / Orchestration Core

Resolves Problem #1 and Problem #4

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:62`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:21`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:20`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:32`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:62`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:34`

Concrete replacement logic:
- Create `backend/app/services/workflow/` with `clock.py`, `contracts.py`, `errors.py`, `state_machine.py`, `dispatcher.py`, `result_mapper.py`, and `orchestrator.py`.
- Move `WorkflowOrchestrator` logic into `workflow/orchestrator.py`; leave `workflow_orchestrator.py` as a thin facade exporting the class from the new package.
- Split `playbook_run_executor.py` into `execution_session.py`, `callback_bridge.py`, `result_persistence.py`, and `runtime_provider_loader.py`.
- Split `decision/coordinator.py`, `governance_engine.py`, `meeting/engine.py`, and `dispatch_orchestrator.py` by concern: branch planning, policy checks, meeting turn execution, dispatch attempt tracking.
- Extract `_prompts.py` string/template handling into a prompt catalog package so meeting orchestration does not import large prompt literals directly.

Verification commands:

```bash
pytest backend/tests/test_workflow_orchestrator_remote_tool_routes.py \
  backend/tests/test_execution_plan_flow.py \
  backend/tests/test_execution_runner_metadata.py \
  backend/tests/test_playbook_runner_routing.py
```

### Wave 2: Conversation / Task / Artifact Pipeline

Resolves Problem #2

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_builder.py:34`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/task_manager.py:32`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/artifact_extractor.py:27`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/artifact_extractor.py:27`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_executor.py:24`

Concrete replacement logic:
- Create `backend/app/services/conversation/planning/`, `tasks/`, `actions/`, `context/`, and `artifacts/`.
- Canonicalize artifact extraction in one location only: migrate all callers to `backend.app.services.conversation.artifacts.extractor`, add a temporary import shim from `backend.app.services.artifact_extractor`, then delete the unused conversation copy after a final grep proves zero callers.
- Split `plan_builder.py` into `intent_selection.py`, `side_effect_policy.py`, `llm_model_selection.py`, `pack_resolution.py`, and `trace_logging.py`.
- Split `task_manager.py` into `task_lifecycle.py`, `timeline_projection.py`, `artifact_attachment.py`, and `timeout_monitor.py`.
- Split `suggestion_action_handler.py`, `cta_handler.py`, and `plan_executor.py` into command handlers plus shared DTOs so confirmation logic, action execution, and output shaping stop living together.
- Move `context_builder/builder.py` to a package with `collectors.py`, `formatters.py`, `budgeting.py`, and `prompt_builder.py`.

Verification commands:

```bash
pytest backend/tests/test_real_conversation.py \
  backend/tests/test_task_execution_projection.py \
  backend/tests/test_artifacts_phase0.py \
  backend/tests/test_artifacts_route.py \
  backend/tests/test_prompt_builder_runtime_profile_injection.py
```

### Wave 3: Installer / Registry / Tooling Backbone

Resolves Problem #3

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/__init__.py:1-13`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_installer.py:1-23`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_registry.py:19`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/runtime_assets_installer.py:20`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tools/workspace_tools.py:14`

Concrete replacement logic:
- Create `backend/app/services/installers/`, `registry/`, `tooling/`, and `embeddings/`.
- Treat `deprecated/capability_installer.py` as archival cleanup: do not refactor it further. Replace doc references with the new modular installer map, then remove or quarantine the file behind an explicit deprecation shim.
- Split `tool_registry.py` into `models.py`, `discovery.py`, `registry_store.py`, `resolver.py`, and `capability_bridge.py`.
- Split `playbook_registry.py` into source loaders, manifest loaders, cache/index, and query service modules.
- Split `runtime_assets_installer.py` and `playbook_installer.py` into `manifest_loader.py`, `validator.py`, `installer.py`, `rollback.py`, and `reporting.py`.
- Split `tool_embedding_service.py` into `embedding_provider.py`, `chunking.py`, `index_writer.py`, and `reindex_job.py`.
- Split `workspace_tools.py` into one file per workspace tool or tool family, with shared path guards and serializers.

Verification commands:

```bash
pytest backend/tests/test_runtime_assets_installer.py \
  backend/tests/test_playbook_registry_smoke.py \
  backend/tests/test_tool_embedding_service.py \
  backend/tests/test_workspace_execution_tools.py \
  backend/tests/test_tool_rag_cache.py
```

### Wave 4: API Surface and Provider Boundary

Resolves Problem #1 and Problem #4

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:35`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/cloud_providers.py:22`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/mindscape/routes.py:39`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/executions.py:45`

Concrete replacement logic:
- Convert `playbook_execution.py` into a package: `router.py`, `schemas.py`, `handlers/start.py`, `handlers/control.py`, `handlers/debug.py`, `dependencies.py`, and `response_mappers.py`.
- Convert `cloud_providers.py` into a package separating provider schemas, provider factory/resolver, credential validation, and HTTP handlers.
- Split `backend/features/mindscape/routes.py` by domain endpoint families instead of one mega-route module.
- Split `backend/features/workspace/executions.py` into stream events, read endpoints, write endpoints, SSE transport, and response projection helpers.
- Keep original route import surfaces stable by re-exporting `router` objects from the new packages during migration.

Verification commands:

```bash
pytest backend/tests/test_api_execution_coordinator.py \
  backend/tests/test_queue_position_cache.py \
  backend/tests/test_running_server_routes.py \
  backend/tests/test_execution_chat_agent_service.py
```

### Wave 5: Workspace / Settings Frontend

Resolves Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/PendingTasksPanel.tsx:211`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/TimelinePanel.tsx:133`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/wizards/LocalFilesystemManagerContent.tsx:149`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/components/CliApiKeysSection.tsx:206`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/panels/ModelsAndQuotaPanel.tsx:57`

Concrete replacement logic:
- Create `web-console/src/app/workspaces/components/pending-tasks/` and split `PendingTasksPanel.tsx` into `PendingTasksPanelShell.tsx`, `usePendingTasksState.ts`, `PendingTaskList.tsx`, `RejectDialog.tsx`, and `PlaybookIntentSubtitle.tsx`.
- Create `web-console/src/app/workspaces/components/timeline/` and split `TimelinePanel.tsx` into `TimelinePanelShell.tsx`, `useTimelineFeed.ts`, `TimelineList.tsx`, `TimelineFilters.tsx`, and `TimelineDetailDrawer.tsx`.
- Create `web-console/src/app/settings/components/local-filesystem/` for `LocalFilesystemManagerContent` sections, form schema, and API adapter.
- Create `web-console/src/app/workspaces/[workspaceId]/components/runtime-api-keys/` for `CliApiKeysSection` state, API client, pool editor, and provider card subcomponents.
- Create `web-console/src/app/settings/components/model-quota/` for `ModelsAndQuotaPanel` and stop pulling workspace runtime UI directly from a monolithic settings panel.
- Remove inline debug `console.log` statements from extracted hooks after parity is proven.

Verification commands:

```bash
cd web-console
npm run type-check
npm run lint
npx vitest run \
  src/contexts/__tests__/MessagesContext.merge.test.ts \
  src/app/workspaces/[workspaceId]/instruction/page.test.tsx \
  src/lib/__tests__/time.test.ts
```

---

## Phase 5: Citation Audit (CoVe Final Pass)

Critical citations re-verified while writing this plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:1-80`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_builder.py:1-90`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:1-110`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/task_manager.py:20-80`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_installer.py:1-23`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/__init__.py:1-13`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/PendingTasksPanel.tsx:1-260`

Assumption checks re-verified:
- No runtime caller for `CapabilityInstaller(` in `backend/` and `scripts/`
- No caller for `conversation.artifact_extractor`
- Current frontend mount points exist for all five large UI components

---

## Phase 6: Validation SOP

### Step-by-step SOP

1. Create the PostgreSQL backup before the first extraction commit.
2. Land Wave 1 package skeletons and compatibility facades without moving behavior yet.
3. Move one cluster at a time, keeping old import paths as shims until tests pass.
4. After each wave, run the wave-specific commands plus a focused manual check.
5. Only remove deprecated or duplicate files after a final full-project grep shows zero live imports.

### Manual verification scenarios

1. **Workspace execution happy path**
   - Start a playbook execution from the workspace UI.
   - Pass: execution appears in timeline, task panel updates, no route import errors, callbacks persist.
   - Fail: missing status updates, route 500s, or orphan task records.
2. **Conversation-to-artifact path**
   - Run a playbook that produces an artifact through the conversation/task pipeline.
   - Pass: artifact is created once, appears in task outcome/timeline, and no duplicate extractor path is referenced.
   - Fail: artifact missing, duplicated, or version numbering regresses.
3. **Settings/runtime panels**
   - Open Basic Settings, Local Filesystem Manager, and workspace runtime settings modal.
   - Pass: models/quota data renders, API keys section works, storage path editor loads in both mounting locations.
   - Fail: hydration errors, duplicated network requests, or missing section state.

### API verification

Use the running local-core server and replace placeholders with valid IDs:

```bash
curl -sS "http://localhost:8200/api/v1/playbooks/execute/${EXECUTION_ID}/debug/screenshot?file=${FILE_NAME}"
curl -sS "http://localhost:8200/api/v1/playbooks/executions?workspace_id=${WORKSPACE_ID}"
curl -sS "http://localhost:8200/api/v1/cloud/providers"
```

Pass criteria:
- Responses remain schema-compatible with the pre-refactor behavior.
- No new import-cycle startup failures or missing dependency errors appear.

Fail criteria:
- Any endpoint moves behavior without an explicit contract migration.
- Any removed file path still has live callers.

---

## Phase 7: Evaluation & Automated Testing SOP

### Backend tests to add or tighten

1. **Execution state-machine contract**
   - Input: a multi-step handoff plan with one recoverable failure and one successful retry
   - Mock setup: fake tool executor, fake step loop, fixed UTC clock
   - Expected output: state transitions stay stable and result mapper emits the same final status
   - Prevents: Problem #1
2. **Conversation artifact canonicalization**
   - Input: task result payloads for planning, drafting, and generic outputs
   - Mock setup: one canonical artifact extractor module, fake store/path resolver
   - Expected output: exactly one extractor path is used and artifact versioning stays deterministic
   - Prevents: Problem #2
3. **Installer/registry seam protection**
   - Input: sample manifest with playbooks, runtime assets, and missing fields
   - Mock setup: isolated temp capability directory and mocked registry store
   - Expected output: validators reject bad manifests, installers do not call deprecated installer code, registry cache stays coherent
   - Prevents: Problem #3
4. **Route handler contract tests**
   - Input: start, resume, cancel, and provider-list HTTP requests
   - Mock setup: fake execution service and provider resolver injected at handler layer
   - Expected output: route modules only translate HTTP payloads and do not require orchestration internals
   - Prevents: Problem #4

### Frontend tests to add or tighten

1. **Pending tasks hook parity**
   - Input: task lists with background tasks, rejected tasks, and artifact warnings
   - Mock setup: fake workspace context plus mocked fetch responses
   - Expected output: extracted hook returns the same filtered task sets and count callbacks as the legacy panel
   - Prevents: Problem #5
2. **Timeline feed projection**
   - Input: mixed timeline items with loading and retry states
   - Mock setup: fake API layer and mocked time helpers
   - Expected output: list projection, filters, and status labels stay identical after extraction
   - Prevents: Problem #5
3. **Settings composition smoke**
   - Input: mock model/provider config and workspace runtime data
   - Mock setup: render `ModelsAndQuotaPanel` shell plus extracted `CliApiKeysSection`
   - Expected output: settings panel composes the same sub-sections without circular imports
   - Prevents: Problem #5

If some UI tests are not immediately feasible, keep `npm run type-check` and `npm run lint` as mandatory gates and add vitest coverage for each extracted hook before deleting the monolithic source block it came from.

---

## Appendix A: Covered Files and Target Landing Zones

### Wave 1

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py` -> `backend/app/services/workflow/{orchestrator.py,state_machine.py,dispatcher.py,result_mapper.py,errors.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py` -> `backend/app/services/execution/{session.py,callback_bridge.py,result_persistence.py,runtime_provider_loader.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py` -> `backend/app/services/execution_runner/{launcher.py,task_bridge.py,status_reader.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py` -> `backend/app/services/decision/{branching.py,proposal_emitter.py,decision_state.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py` -> `backend/app/services/orchestration/governance/{policy.py,task_emitter.py,follow_up.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py` -> `backend/app/services/orchestration/meeting/{engine.py,turn_runner.py,result_types.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py` -> `backend/app/services/orchestration/meeting/prompts/{catalog.py,render.py,templates.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py` -> `backend/app/services/orchestration/dispatch/{dispatcher.py,attempt_store.py,phase_state.py}`

### Wave 2

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_builder.py` -> `backend/app/services/conversation/planning/{intent_selection.py,side_effect_policy.py,model_selection.py,pack_resolution.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/task_manager.py` -> `backend/app/services/conversation/tasks/{lifecycle.py,timeline_projection.py,artifact_attachment.py,timeout_monitor.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/artifact_extractor.py` -> `backend/app/services/conversation/artifacts/{extractor.py,playbook_extractors.py,storage.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/artifact_extractor.py` -> archive after callers are consolidated on the canonical extractor path
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/suggestion_action_handler.py` -> `backend/app/services/conversation/actions/{suggestions.py,command_handlers.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_executor.py` -> `backend/app/services/conversation/execution/{executor.py,tool_dispatch.py,write_actions.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/intent_analyzer.py` -> `backend/app/services/playbook/intent/{analyzer.py,prompt_builder.py,parser.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/conversation_manager.py` -> `backend/app/services/playbook/conversation/{manager.py,state.py,serialization.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/context_builder/builder.py` -> `backend/app/services/conversation/context/{builder.py,collectors.py,formatters.py,budgeting.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/cta_handler.py` -> `backend/app/services/conversation/actions/{cta.py,confirmation.py}`

### Wave 3

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/capability_installer.py` -> archive/remove after doc references migrate to modular installers
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_registry.py` -> `backend/app/services/registry/{models.py,discovery.py,resolver.py,cache.py,capability_bridge.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_registry.py` -> `backend/app/services/playbook_registry/{sources.py,manifest_loader.py,index.py,query.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/runtime_assets_installer.py` -> `backend/app/services/installers/runtime_assets/{validator.py,installer.py,rollback.py,reporting.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_installer.py` -> `backend/app/services/installers/playbooks/{validator.py,installer.py,compat.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_embedding_service.py` -> `backend/app/services/embeddings/{provider.py,chunking.py,index_writer.py,reindex_job.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tools/workspace_tools.py` -> `backend/app/services/tools/workspace/{catalog.py,path_guard.py,serializers.py,<tool_family>.py}`

### Wave 4

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py` -> `backend/app/routes/core/playbook_execution/{router.py,schemas.py,handlers/,dependencies.py,response_mappers.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/cloud_providers.py` -> `backend/app/routes/core/cloud_providers/{router.py,schemas.py,provider_factory.py,validators.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/mindscape/routes.py` -> `backend/features/mindscape/routes/{router.py,entity_handlers.py,tag_handlers.py,schemas.py}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/executions.py` -> `backend/features/workspace/executions/{router.py,streaming.py,queries.py,mutations.py,response.py}`

### Wave 5

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/PendingTasksPanel.tsx` -> `web-console/src/app/workspaces/components/pending-tasks/{PendingTasksPanelShell.tsx,usePendingTasksState.ts,PendingTaskList.tsx,RejectDialog.tsx,PlaybookIntentSubtitle.tsx}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/TimelinePanel.tsx` -> `web-console/src/app/workspaces/components/timeline/{TimelinePanelShell.tsx,useTimelineFeed.ts,TimelineList.tsx,TimelineFilters.tsx,TimelineDetailDrawer.tsx}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/wizards/LocalFilesystemManagerContent.tsx` -> `web-console/src/app/settings/components/local-filesystem/{LocalFilesystemManagerShell.tsx,useLocalFilesystemConfig.ts,PathForm.tsx,ValidationSummary.tsx}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/components/CliApiKeysSection.tsx` -> `web-console/src/app/workspaces/[workspaceId]/components/runtime-api-keys/{CliApiKeysSectionShell.tsx,useCliApiKeys.ts,ProviderPoolEditor.tsx,KeyStatusList.tsx}`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/panels/ModelsAndQuotaPanel.tsx` -> `web-console/src/app/settings/components/model-quota/{ModelsAndQuotaPanelShell.tsx,useModelQuotaState.ts,ProviderCards.tsx,QuotaTables.tsx,RuntimeApiKeysBridge.tsx}`
