# IG Workspace Event Convergence UI Mapping Plan

Date: 2026-03-22

Scope: reverse-engineer the current IG frontend event needs from actual UI entry points, define a canonical local-core event contract, and map every real UI surface to its required transport and ownership.

## Phase 1: Evidence Collection

### Evidence Items

- **E1. Shared workspace SSE already exists and is explicitly designed to multiplex one connection per workspace.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/workspace/eventProjector.ts:571-777`
  - Verified facts:
    - Opens exactly one shared `EventSource` per `workspaceId` at `/api/v1/workspaces/:id/events/stream`.
    - Preserves `payload`, `metadata`, `entity_ids`, `workspace_id`, `project_id`, `profile_id`.
    - Client-side filters subscribers by `eventTypes`.

- **E2. The unified workspace stream already serializes named SSE events with `payload` and `metadata`.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/timeline.py:543-591,658-725`
  - Verified facts:
    - Backend emits `event: {event_type}` plus structured JSON data.
    - `event_data` includes `id`, `type`, `timestamp`, `actor`, `workspace_id`, `project_id`, `profile_id`, `thread_id`, `payload`, `entity_ids`, `metadata`.
    - The route is `/api/v1/workspaces/{workspace_id}/events/stream`.

- **E3. A second, separate raw workspace activity stream also exists.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/workspace/activity_stream.py:1-87`
  - Verified facts:
    - Route is `/api/v1/workspaces/{workspace_id}/activity-stream`.
    - It relays raw Redis pub/sub messages from `workspace:{id}:stream`.
    - Event types documented there are `meeting_stage`, `mind_event`, `task_dispatched`, `dispatch_completed`, `task_completed`.

- **E4. References currently bypasses the shared workspace bus and opens its own `activity-stream` connection.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/ReferencesPanel.tsx:1027-1058`
  - Verified facts:
    - `ReferencesPanel` creates a dedicated `EventSource` to `/activity-stream`.
    - It refreshes list + facets on `task_completed` or `execution_completed`.

- **E5. Discovery state is split across mount-time run-status probing, custom browser events, and per-execution SSE/polling.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/AccountsPanel.tsx:166-320`
  - Verified facts:
    - `AccountsPanel` listens to `mindscape:execution_started`.
    - It dispatches `mindscape:execution_started` after `execute/start`.
    - It also attaches `useExecutionPolling` to the current IG execution.

- **E6. Sources tab currently relies on local CustomEvents for refresh.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/SourcesTab.tsx:68-89`
  - Verified facts:
    - `SourcesTab` refreshes seeds on `mindscape:execution_started`.
    - It also listens for `mindscape:execution_completed`.

- **E7. `mindscape:execution_completed` currently has no dispatcher in IG or local-core web-console scope.**
  - Evidence command:
    - `rg -n "mindscape:execution_completed|new CustomEvent\\('mindscape:execution_completed'|dispatchEvent\\(.*mindscape:execution_completed" /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src -S`
  - Verified facts:
    - The only match is the listener in `SourcesTab.tsx`.
    - No producer exists in the searched scope.

- **E8. Seed dropdown optimistic updates currently depend on local start-event inputs, not backend canonical events.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useSeedOptions.ts:74-104`
  - Verified facts:
    - `useSeedOptions` reads `detail.inputs.target_username` from `mindscape:execution_started`.
    - It optimistically inserts that seed before backend refresh.

- **E9. Account detail batch-pin status depends on local start-event routing plus per-execution polling.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx:388-444`
  - Verified facts:
    - `AccountDetailPanel` listens to `mindscape:execution_started`.
    - It only attaches `useExecutionPolling` when `activeInsightTab === 'posts'`.
    - Terminal handling is done via execution stream end / completion events.

- **E10. Right-side run logs pin themselves via local start events.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useExecutionState.ts:120-149`
  - Verified facts:
    - `useExecutionState` listens to `mindscape:execution_started`.
    - It switches to `logs` and sets `forcedExecution` for `ig_analyze_following`.

- **E11. Multiple IG start paths manually dispatch `mindscape:execution_started`.**
  - Evidence:
    - `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/hooks/useIGWorkbenchState.ts:425-439`
    - `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/followingAnalyzer/hooks/useFollowingAnalyzerExecution.ts:497-512`
    - `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useImportHandles.ts:59-76`
    - `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useExecutionActions.ts:100-124`
  - Verified facts:
    - Start notification is currently produced ad hoc by several frontend callers.
    - The event shape is similar but duplicated.

- **E12. Accounts status bootstrap still probes executions + progress/status endpoints directly.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useAccountsRunStatus.ts:83-313`
  - Verified facts:
    - It fetches `/executions?limit=30&playbook_code_prefix=ig_`.
    - It probes `/executions/{id}/progress-snapshot`.
    - It probes `/playbooks/execute/{id}/status`.

- **E13. Backend already writes unified `RUN_STATE_CHANGED` MindEvents for READY, RUNNING, and DONE.**
  - Evidence:
    - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:256-289`
    - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:416-449`
    - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:525-558`
  - Verified facts:
    - `payload` already includes `execution_id`, `previous_state`, `new_state`, `reason`, `playbook_code`.
    - `metadata` currently only includes `playbook_code`.

- **E14. Backend raw activity terminal event is minimal and separate from the unified stream.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/stores/tasks_store/_base.py:682-745`
  - Verified facts:
    - Raw `task_completed` publishes `task_id`, `execution_id`, `status`, `pack_id`, `thread_id`.
    - This path goes to Redis `workspace:{ws_id}:stream`, not `MindEvent`.

- **E15. Unified terminal coverage is incomplete: failed/cancelled lifecycle is not emitted as `RUN_STATE_CHANGED`.**
  - Evidence:
    - Failure path only updates task status: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:631-636`
    - Failure helper only updates task record: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/task_manager.py:100-119`
    - Cancellation endpoint updates task status directly: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:793-830`
  - Verified facts:
    - READY/RUNNING/DONE exist in unified stream.
    - FAILED/CANCELLED currently rely on task-table state and raw activity events, not unified `MindEvent` lifecycle.

- **E16. Runtime logs still show repeated IG requests across seeds/status/progress/debug endpoints.**
  - Evidence command:
    - `docker logs --tail 400 mindscape-ai-local-core-backend 2>&1 | rg -n "/api/v1/ig/insights/seeds|/api/v1/ig/insights/seed-status|/api/v1/workspaces/.*/progress-snapshot|/api/v1/playbooks/execute/.*/status|/api/v1/workspaces/.*/executions\\?limit=30&playbook_code_prefix=ig_" -S`
  - Verified facts:
    - Recent backend logs show repeated calls to `seeds`, `seed-status`, `progress-snapshot`, `execute/:id/status`, and grouped executions.
    - This confirms the transport split is not theoretical; it produces real request churn.

- **E17. The actual IG UI entry surface is finite and centrally registered.**
  - Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/IGWorkbench.tsx:119-339`
  - Verified facts:
    - Actual top-level modules are `plan`, `produce`, `assets`, `references`, `access`, `review`, `export`, `publish`, `measure`, `engage`, `discovery`, `managed`, plus default `grid`, `timeline`, `kanban`.

- **E18. Full-project grep shows current live-event consumers are concentrated in discovery, references, workbench, and following-analyzer surfaces.**
  - Evidence command:
    - `rg -n "eventProjector|activity-stream|useExecutionPolling|mindscape:execution_started|mindscape:execution_completed|EventBus|events/stream" /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui -S`
  - Verified facts:
    - Direct live-event usage appears in `ReferencesPanel`, `AccountsPanel`, `SourcesTab`, `useSeedOptions`, `AccountDetailPanel`, `useAccountsRunStatus`, `useExecutionState`, `useIGWorkbenchState`, `useExecutionActions`, `useFollowingAnalyzerExecution`, and workbench polling hooks.
    - No direct live-event consumption was found in `ProducePanel`, `AssetsPanel`, `ReviewPanel`, `ExportPanel`, `PublishPanel`, `MeasurePanel`, `EngagePanel`, `AccessPanel`, `ManagedAccountsPanel`, default `IGGridView`, `TimelineView`, or `KanbanView` within that grep scope.

## Phase 1.5: Historical Regression Analysis

| History Item | Exact Change | Why it seemed correct | Why it did not solve the structural problem |
|---|---|---|---|
| H1 | Commit `b93f5c3` broadened `ReferencesPanel` refresh trigger from `pack_id.startsWith('ig')` to any `task_completed/execution_completed`. | `pack_id` on raw activity events was unreliable, so broadening avoided missed refreshes. | It still kept `ReferencesPanel` on its own raw `activity-stream`, so transport fragmentation remained. |
| H2 | Commit `d8ef82f` changed References SSE refresh to background mode to avoid the loading spinner. | This reduced visible UI jank when SSE bursts arrived. | It treated the symptom only. The panel still owned its own transport and still refreshed from raw task-completion events. |
| H3 | Recent IG fixes in working tree reduced overfetch (`refresh_head`) and duplicate pollers, but did not define a single canonical event contract. | Payload size and duplicate polling were immediate bottlenecks and needed relief. | The core failure mode remains: each UI still decides its own transport and fallback shape. |

**Regression conclusion:** previous fixes correctly reduced missed refreshes and visible jank, but they operated at the consumer level. None of them converged IG onto a single canonical workspace event contract. The new plan must avoid introducing “one more local event” or “one more direct stream.”

## Phase 2: Problem Definition + Severity Scoring

1. **[Canonical contract missing]**: IG has no single pack-scoped lifecycle contract across UIs, so each surface infers state from a different transport or payload shape. (E1, E2, E4, E5, E8, E13, E15)
2. **[Transport fragmentation]**: the same workspace currently mixes shared workspace SSE, raw Redis activity SSE, per-execution SSE, mount-time status probes, and local CustomEvents. (E3, E4, E5, E10, E11, E12, E16)
3. **[Dead terminal event dependency]**: at least one real UI (`SourcesTab`) listens for `mindscape:execution_completed`, but no producer exists. (E6, E7)
4. **[Terminal lifecycle coverage gap]**: unified `MindEvent` lifecycle emits READY/RUNNING/DONE, but FAILED/CANCELLED still bypass that path. (E13, E15)
5. **[Unbounded operational coupling]**: some UIs that only need lifecycle hints are forced to probe expensive detail endpoints because no shared canonical event exists. (E12, E16)

### FMEA-lite

| Problem | Severity | Detection | Priority |
|---|---:|---:|---:|
| Canonical contract missing | 5 | 4 | 20 |
| Terminal lifecycle coverage gap | 5 | 4 | 20 |
| Transport fragmentation | 4 | 4 | 16 |
| Dead terminal event dependency | 4 | 4 | 16 |
| Unbounded operational coupling | 4 | 3 | 12 |

## Phase 3: Assumption Verification (CoVe)

| Assumption | Verification Question | Answer | Evidence |
|---|---|---|---|
| The shared workspace bus can carry IG-specific routing metadata. | Does `/events/stream` actually preserve `payload` and `metadata` end-to-end? | Yes. Backend serializes them, frontend preserves them in `UnifiedEvent`. | E1, E2 |
| The backend has a legitimate insertion point for canonical IG lifecycle metadata. | Where are execution lifecycle events currently created? | `playbook_runner.py` already creates READY/RUNNING/DONE `RUN_STATE_CHANGED` events. | E13 |
| Sources terminal refresh can currently fire from local custom events. | Is `mindscape:execution_completed` dispatched anywhere? | No. Only a listener exists. | E7 |
| Replacing every per-execution stream with workspace SSE is safe. | Which UIs still need high-frequency detail progress rather than coarse lifecycle? | `AccountsPanel`, `AccountDetailPanel`, `WorkbenchExecutionPanel`, and `FollowingAnalyzer` still need per-execution progress/debug. | E5, E9, E12 |
| Not every IG module needs event convergence work in this phase. | Which actual IG surfaces currently consume live events? | Only discovery, references, workbench, and following-analyzer surfaces matched the live-event grep. | E18 |

## Phase 3.5: Pre-Mortem

### Failure Mode 1: Workspace bus does not expose enough IG routing metadata

- Risk: frontend convergence stalls because the bus only says “RUNNING” without target seed/reference/profile context.
- Ruled out? No.
- Mitigation in plan:
  - explicitly enrich `metadata` and `payload` in `playbook_runner.py` at READY/RUNNING/DONE
  - add matching FAILED/CANCELLED unified events

### Failure Mode 2: We remove per-execution polling from places that actually need detailed progress

- Risk: Targets/Run Logs regress from live per-step progress back to coarse status only.
- Ruled out? No.
- Mitigation in plan:
  - keep `useExecutionPolling` only for detail/progress surfaces
  - use workspace bus only for lifecycle fan-out and refresh hints

### Failure Mode 3: Start latency becomes perceptibly worse if local optimistic events are removed too early

- Risk: logs panel or target views feel slower because the first canonical event arrives after the HTTP start round-trip + stream polling interval.
- Ruled out? No.
- Mitigation in plan:
  - keep a thin local optimistic adapter for “focus/pin immediately”
  - stop using that adapter as source-of-truth for terminal state or refresh correctness

## Phase 4: Implementation Plan

### 0. Data Backup Warning

This implementation and validation can create new executions, progress artifacts, and workspace records. Perform a backup before testing:

```bash
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
```

### 1. Define the canonical IG workspace lifecycle contract

Resolves Problem #1, #2, #4

**Backend owner:** local-core runtime/event layer

**Insertion points verified:**
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:264-284`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:424-444`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:533-553`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:631-636`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:793-830`

**Required canonical metadata contract for IG lifecycle events:**

```json
{
  "metadata": {
    "pack_id": "ig",
    "playbook_code": "ig_analyze_following",
    "execution_id": "<uuid>",
    "lifecycle_state": "READY|RUNNING|DONE|FAILED|CANCELLED",
    "terminal": false,
    "ui_surface": "discovery|references|workbench|following_analyzer",
    "refresh_hint": ["sources", "targets", "references", "run_logs"],
    "target_username": "kachuuu____",
    "target_handle": "kachuuu____",
    "reference_id": "ref_xxx",
    "user_data_dir": "/app/data/ig-browser-profiles/default"
  }
}
```

**Precise implementation logic:**

1. In `playbook_runner.py`, replace the current `metadata={"playbook_code": playbook_code}` with a helper-generated metadata object for READY/RUNNING/DONE.
2. The helper must derive:
   - `pack_id` from `playbook_code` prefix
   - `execution_id` from the live execution
   - `lifecycle_state`
   - `terminal`
   - `target_username` or `target_handle` from `inputs`
   - `reference_id` when present in `inputs`
   - `user_data_dir` when present in `inputs`
   - `refresh_hint` using a small mapping table:
     - `ig_analyze_following` → `["sources", "targets", "run_logs"]`
     - `ig_capture_account_snapshot` → `["captures", "run_logs"]`
     - `ig_analyze_pinned_reference` / `ig_batch_pin_references` → `["references", "run_logs"]`
3. In `playbook_runner.py` exception path, emit a unified FAILED `RUN_STATE_CHANGED` event before or immediately after `update_task_status_to_failed(...)`.
4. In `playbook_execution.py` cancel route, emit a unified CANCELLED `RUN_STATE_CHANGED` event after the task update succeeds.

### 2. Introduce one IG-specific frontend adapter for the shared workspace bus

Resolves Problem #1, #2, #3, #5

**Frontend owner:** IG capability UI

**Insertion points verified:**
- Shared bus provider: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/workspace/eventProjector.ts:571-777`
- Current IG live consumers: E4-E12

**Files to add:**
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/hooks/useIGWorkspaceEvents.ts`
- installed mirror under local-core after pack deploy

**Adapter responsibilities:**

1. Subscribe only once per component tree through `subscribeEventStream(...)`.
2. Filter to IG-relevant events by checking:
   - `event.type === "run_state_changed"` for canonical lifecycle
   - optionally `event.type === "artifact_created"` / `artifact_updated"` later, not in phase 1
3. Normalize helpers:
   - `isIGEvent(event)`
   - `getIGLifecycle(event)`
   - `matchesPlaybook(event, code)`
   - `hasRefreshHint(event, "references" | "sources" | "targets" | "run_logs" | "captures")`

**Important boundary rule:**
- This hook is the only place inside IG that should know `subscribeEventStream`.
- All pack-local components consume normalized helpers, not raw `EventSource`.

### 3. UI-by-UI convergence mapping

Resolves Problem #1, #2, #3, #5

| UI Surface | Entry File | Current State Source | What the UI actually needs | Target Source | Keep per-exec polling? |
|---|---|---|---|---|---|
| References module | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/ReferencesPanel.tsx` | Direct `/activity-stream` + HTTP refresh | Terminal lifecycle hint to refresh list/facets | `useIGWorkspaceEvents` with `refresh_hint=references` | No |
| Discovery / Sources | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/SourcesTab.tsx` | `mindscape:execution_started` + dead `mindscape:execution_completed` | Refresh seed cards when following run starts/ends | `useIGWorkspaceEvents` with `refresh_hint=sources` | No |
| Discovery / Seed dropdown | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useSeedOptions.ts` | `mindscape:execution_started.detail.inputs.target_username` | Optimistic seed insertion plus eventual refresh | Local optimistic adapter for immediate insert, workspace bus for canonical refresh | No |
| Discovery / Targets shell | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/AccountsPanel.tsx` | `useAccountsRunStatus` + `mindscape:execution_started` + `useExecutionPolling` | Pin active following/capture execution, refresh counts/cards on lifecycle changes | workspace bus for lifecycle, keep `useExecutionPolling` for detailed stages | Yes |
| Discovery / Account detail posts tab | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx` | `mindscape:execution_started` + `useExecutionPolling` | Track active batch-pin run for a specific handle and refresh posts on terminal | workspace bus for start/terminal pinning, per-exec polling for summary | Yes |
| Following Analyzer overlay | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/followingAnalyzer/hooks/useFollowingAnalyzerExecution.ts` | direct start + `useExecutionPolling` + local custom event dispatch | Detailed execution progress + immediate workbench awareness | keep `useExecutionPolling`, emit canonical workspace lifecycle from backend, keep optional local optimistic pin | Yes |
| Right Run Logs / forced execution | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useExecutionState.ts` and `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useIGDebug.ts` | `mindscape:execution_started` + grouped run refresh + selected execution debug fetches | Switch to logs tab, pin latest IG execution, and fetch selected execution debug details | workspace bus for lifecycle pinning; keep `useIGDebug`/selected execution polling only for focused debug detail | Yes, only for selected active execution |
| Workbench start actions | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/hooks/useIGWorkbenchState.ts` and `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useExecutionActions.ts` | manual dispatch of `mindscape:execution_started` | immediate UX feedback after successful start/rerun | keep as optimistic UI adapter, but not canonical source-of-truth | N/A |
| Import handles flow | `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useImportHandles.ts` | manual dispatch of `mindscape:execution_started` | immediately pin new following execution | keep as optimistic UI adapter, but not canonical source-of-truth | N/A |
| IG Active Profile / grouped runs | workbench state chain rooted at `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/hooks/useIGWorkbenchState.ts` | grouped executions API + selected execution polling | operational visibility, not reference correctness | continue grouped runs API; refresh trigger should come from workspace bus | Selected run only |
| Discovery / Captures | AccountsPanel + CapturesTab | indirect via parent state | capture lifecycle start/finish only | workspace bus `refresh_hint=captures` via parent | No direct |
| Discovery / Analytics | AccountsPanel + Insights/Analytics tabs | plain API loads | no current live event requirement found | no phase-1 change | No |
| Produce / Assets / Review / Export / Publish / Measure / Engage / Access / Managed / default Grid-Timeline-Kanban | `IGWorkbench.tsx` module entries + grep scope E18 | no direct live-event consumer found | none proven | no phase-1 change | No |

### 4. Replace raw `activity-stream` consumption in References

Resolves Problem #1, #2

**Insertion points verified:**
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/ReferencesPanel.tsx:1027-1058`

**Precise replacement logic:**

1. Delete the direct `new EventSource(${apiUrl}/api/v1/workspaces/${workspaceId}/activity-stream)` block.
2. Replace it with `useIGWorkspaceEvents(...)`.
3. Trigger the existing debounced `refresh_head` + `fetchFacets()` only when:
   - `event.type === "run_state_changed"`
   - `event.metadata.pack_id === "ig"`
   - `event.metadata.terminal === true`
   - `event.metadata.refresh_hint` contains `"references"`
4. Do not re-introduce direct `task_completed` coupling.

### 5. Remove dead completion coupling from Sources and canonicalize seed refresh

Resolves Problem #3, #5

**Insertion points verified:**
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/SourcesTab.tsx:68-89`
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useSeedOptions.ts:74-104`

**Precise replacement logic:**

1. Remove `mindscape:execution_completed` listener entirely.
2. Move canonical refresh behavior to `useIGWorkspaceEvents(...)`:
   - start or terminal event
   - `metadata.playbook_code === "ig_analyze_following"`
   - `refresh_hint` contains `"sources"`
3. Keep one small local optimistic path in `useSeedOptions` for immediate dropdown insertion from just-started inputs.
4. Canonical backend refresh must come from workspace bus, not browser-only events.

### 6. Narrow per-execution polling to detail-only surfaces

Resolves Problem #2, #5

**Insertion points verified:**
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/hooks/useAccountsRunStatus.ts:83-313`
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/AccountsPanel.tsx:280-320`
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/accounts/components/AccountDetailPanel.tsx:412-444`
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/usePolling.ts:22-57`
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useIGDebug.ts:25-218`
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/followingAnalyzer/hooks/useFollowingAnalyzerExecution.ts:430-440`

**Boundary after convergence:**

- Workspace bus responsibilities:
  - new execution became relevant to UI
  - terminal execution completed/failed/cancelled
  - general refresh hints for module-level data
- Per-execution polling responsibilities:
  - detailed stage progress
  - artifact-backed progress snapshots
  - selected execution debug views

**Implementation detail:**
- `useAccountsRunStatus` remains only as page-load bootstrap for “already-running when page opened.”
- After bootstrap, lifecycle changes should come from workspace bus.
- `progress-snapshot` and `/status` must stay attached only to a selected or currently active execution.
- `useIGDebug` is explicitly part of that selected-execution-only boundary; it must not become a module-level refresh trigger.

### 7. Canonicalize the optimistic local adapter

Resolves Problem #1, #2

**Current producers verified:**
- `useIGWorkbenchState.ts`
- `useFollowingAnalyzerExecution.ts`
- `useImportHandles.ts`
- `useExecutionActions.ts`
- `AccountsPanel.tsx`

**Plan:**

1. Keep one temporary local event: `mindscape:execution_started`.
2. Rename its role in code comments to “optimistic UI adapter,” not “SSE source.”
3. Standardize payload keys:
   - `workspaceId`
   - `executionId`
   - `playbookCode`
   - `inputs`
   - `startedAt`
4. Stop adding any new local custom events beyond this adapter.
5. Do not use local custom events for terminal correctness.

## Phase 5: Citation Audit

Critical citations re-checked after drafting:

- Shared workspace SSE transport:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/workspace/eventProjector.ts:602-617`
- Backend unified stream payload format:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/timeline.py:555-591`
- References raw activity-stream consumer:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/ui/modules/ReferencesPanel.tsx:1027-1047`
- Unified lifecycle emission insertion points:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:264-283`
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:424-443`
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:533-552`
- Failure/cancel gaps:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:631-636`
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:821-828`

## Phase 6: Validation SOP

### Scenario A: References terminal refresh uses the canonical workspace bus

Problem coverage: #1, #2

1. Open IG `References`.
2. Trigger a pinned-reference analysis or batch pin analysis.
3. Observe network panel.

Pass:
- no direct `/api/v1/workspaces/:id/activity-stream` connection from `ReferencesPanel`
- one shared `/api/v1/workspaces/:id/events/stream` connection is reused
- terminal lifecycle event refreshes references via `refresh_head`, not full reload

Fail:
- `ReferencesPanel` still opens its own `activity-stream`
- terminal completion no longer refreshes list/facets

### Scenario B: Sources refresh no longer depends on dead completion CustomEvent

Problem coverage: #3, #5

1. Open Discovery → Sources.
2. Start `ig_analyze_following`.
3. Let it complete or cancel.
4. Observe whether seed cards refresh.

Pass:
- Sources refreshes on canonical workspace lifecycle even if no browser-local completion event is dispatched
- removing `mindscape:execution_completed` listener does not regress refresh

Fail:
- Sources only refreshes when reloading the page
- a browser-only event is still required for terminal refresh

### Scenario C: Targets/Run Logs still show live progress

Problem coverage: #2, #5

1. Start `ig_analyze_following`.
2. Keep Discovery → Targets open.
3. Keep right Run Logs visible.

Pass:
- active execution pins immediately
- per-step progress still updates
- operational endpoints are limited to the selected/active execution path, not every module

Fail:
- detailed progress disappears after removing transport coupling
- requests still storm across seeds/status/progress for non-selected surfaces

### Scenario D: Failed and cancelled runs arrive on the unified bus

Problem coverage: #4

1. Trigger one IG execution that fails.
2. Trigger one IG execution and cancel it via `/api/v1/playbooks/execute/{id}/cancel`.
3. Inspect `/events/stream` payloads and UI reactions.

Pass:
- unified `run_state_changed` events exist for FAILED and CANCELLED
- metadata includes `pack_id`, `playbook_code`, `execution_id`, `terminal=true`

Fail:
- FAILED/CANCELLED still appear only in task-table/raw activity paths

## Phase 7: Evaluation & Automated Testing SOP

### Backend tests

1. **Lifecycle metadata enrichment test**
   - Target: `playbook_runner.py`
   - Setup:
     - mock `self.store.create_event`
     - run a minimal IG playbook start path
   - Expected:
     - READY/RUNNING/DONE `RUN_STATE_CHANGED` events contain `metadata.pack_id == "ig"`
     - metadata includes `execution_id`, `playbook_code`, `terminal`, `refresh_hint`
   - Protects: Problems #1, #4

2. **Failure lifecycle emission test**
   - Target: `playbook_runner.py`
   - Setup:
     - make execution fail after task creation
   - Expected:
     - FAILED `RUN_STATE_CHANGED` emitted once
     - `terminal == true`
   - Protects: Problem #4

3. **Cancellation lifecycle emission test**
   - Target: `playbook_execution.py`
   - Setup:
     - create task, cancel execution
   - Expected:
     - CANCELLED `RUN_STATE_CHANGED` emitted once
   - Protects: Problem #4

### Frontend tests

1. **IG workspace hook filter test**
   - Target: `useIGWorkspaceEvents.ts`
   - Setup:
     - mock `subscribeEventStream`
     - emit mixed workspace events
   - Expected:
     - only IG `run_state_changed` events with matching `metadata.pack_id` flow through
   - Protects: Problems #1, #2

2. **References convergence test**
   - Target: `ReferencesPanel.tsx`
   - Setup:
     - mock workspace event subscription
     - emit terminal IG lifecycle event with `refresh_hint=["references"]`
   - Expected:
     - `fetchReferences('refresh_head', true)` and `fetchFacets()` run
     - no direct `EventSource(activity-stream)` creation
   - Protects: Problems #1, #2

3. **Sources no-dead-event regression test**
   - Target: `SourcesTab.tsx`
   - Setup:
     - do not emit `mindscape:execution_completed`
     - emit canonical workspace terminal event instead
   - Expected:
     - seed list refreshes
   - Protects: Problem #3

4. **SeedOptions optimistic + canonical reconciliation test**
   - Target: `useSeedOptions.ts`
   - Setup:
     - fire optimistic local start adapter with `inputs.target_username`
     - later emit canonical workspace event
   - Expected:
     - seed appears immediately once
     - backend refresh reconciles without duplicate entries
   - Protects: Problems #1, #5

5. **Run Logs lifecycle pinning test**
   - Target: `useExecutionState.ts`
   - Setup:
     - emit canonical workspace READY/RUNNING event for `ig_analyze_following`
   - Expected:
     - active tab switches to logs
     - forced execution set from canonical event
   - Protects: Problems #1, #2

## Deliverable Summary

This plan intentionally does **not** propose “replace everything with workspace SSE.” The correct split is:

- **Canonical workspace bus** for module-level lifecycle and refresh hints
- **Per-execution SSE/polling** only for detail/progress surfaces
- **One temporary optimistic local adapter** for instant focus after start

That split is the only version supported by the current code evidence. Anything broader would repeat the previous failure mode of fixing symptoms while keeping the transport graph fragmented.
