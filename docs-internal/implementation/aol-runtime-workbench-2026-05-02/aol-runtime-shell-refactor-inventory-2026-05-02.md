# AOL Runtime Shell Refactor Inventory

Date: 2026-05-02

Status: First-pass refactor inventory before the AOL Runtime Workbench UX/UI iteration.

## Purpose

This document lists the files over 500 lines that are in scope for the first refactor pass around the AOL Runtime Shell, Meeting Workbench, object runtime, meeting graph projection, and pack-owned IG/PD integration boundaries.

This pass should reorganize the implementation tree and perform the architecture rename. It should not redesign the end-user workbench experience yet.

Target naming:

```text
AOL Runtime Shell      = architecture/runtime host
AOL Runtime Workbench  = user-facing product surface
Meeting Workbench      = meeting-session-centered workbench view
Meeting Graph          = runtime/debug/provenance substrate
Command Ledger         = durable intent and execution ledger
```

## Inventory Commands

Local-core focused count:

```bash
wc -l \
  web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx \
  web-console/src/components/capabilities/AddressableObjectHostShell.tsx \
  web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx \
  web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx \
  'web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx' \
  backend/app/routes/core/workspace/object_runtime.py \
  backend/app/routes/core/workspace/meeting_graph.py \
  backend/app/models/object_runtime.py \
  backend/app/services/orchestration/meeting/engine.py \
  backend/app/services/orchestration/meeting/_prompts.py \
  backend/app/services/orchestration/meeting/_prompt_context.py \
  backend/app/services/orchestration/meeting/_generation.py \
  backend/app/services/orchestration/meeting/_session.py \
  backend/app/services/orchestration/meeting/dispatch_policy_gate.py \
  backend/app/services/orchestration/meeting/_action_items.py
```

Pack-boundary count:

```bash
wc -l \
  capabilities/ig/manifest.yaml \
  capabilities/ig/ui/modules/ReferencesPanel.tsx \
  capabilities/ig/ui/modules/referencesPanel/ReferenceGridCard.tsx \
  capabilities/ig/ui/modules/referencesPanel/ReferenceDetailModal.tsx \
  capabilities/ig/api/references_api_query_routes.py \
  capabilities/ig/services/reference_catalog_read.py \
  capabilities/ig/services/reference_catalog_store.py \
  capabilities/ig/services/reference_index_read.py \
  capabilities/performance_direction/manifest.yaml \
  capabilities/performance_direction/ui/components/PerformanceDirectionStoryboardEditorPage.tsx \
  capabilities/performance_direction/services/object_layer/storyboard_runtime.py \
  capabilities/performance_direction/services/director_guidance.py \
  capabilities/performance_direction/api/__init__.py \
  capabilities/performance_direction/ui/components/storyboardEditor/StoryboardStrip.tsx \
  capabilities/performance_direction/ui/components/storyboardEditor/DepartmentCommandEditorPanel.tsx \
  capabilities/performance_direction/ui/components/storyboardEditor/PerformanceDirectionStartSurface.tsx
```

## P0 Local-Core Refactor Set

These files are directly in the runtime shell and Meeting Workbench path. They should be handled before the second-stage product UX/UI iteration.

| Lines | File | Current role | Refactor action |
| ---: | --- | --- | --- |
| 4181 | `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx` | Monolithic meeting bottom shell: types, projection, fetch, fixed lane canvas, inspector, command bar, object action dispatch, drawer. | Split into Meeting Workbench modules. Keep `AOLMeetingBottomShell.tsx` as compatibility wrapper during migration. |
| 1621 | `web-console/src/components/capabilities/AddressableObjectHostShell.tsx` | Current AOL host/provider/panel/anchor implementation, despite old `AddressableObject` naming. | Introduce `AOLRuntimeShell.tsx` and `AOLRuntimeShellProvider.tsx`; keep old exports as compatibility aliases. |
| 1251 | `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx` | Regression coverage for monolithic bottom shell. | Split specs by extracted modules; retain wrapper smoke tests. |
| 761 | `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx` | Coverage for host shell, bridge, selection, panel, anchors. | Split into shell provider, panel, selection, and anchor tests. |
| 760 | `web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx` | Legacy standalone meeting workbench/admin surface. | Keep as route-level surface; do not use as the new shell architecture root. Rename only if it becomes product-visible. |
| 2774 | `backend/app/routes/core/workspace/object_runtime.py` | Object catalog, selection resolution, actions, materialization, meeting attach, graph projection routes all in one route file. | Split route handlers from object runtime services. Preserve endpoint contracts. |
| 912 | `backend/app/routes/core/workspace/meeting_graph.py` | Meeting execution graph models, projection builder, event merge, bounded graph lookup, route handler. | Move models/projection builder into dedicated model/service modules; leave route thin. |
| 833 | `backend/app/models/object_runtime.py` | All object runtime request/response models in one file. | Split by API surface: refs/catalog, selection, actions, meeting attach/materialize, graph projection. |

## P1 Local-Core Meeting Engine Files

These files are over 500 lines and matter to AOL session feedback, meeting execution, and command-ledger integration. They should not block the shell rename, but they are likely to be touched when the backend command ledger lands.

| Lines | File | Why it matters |
| ---: | --- | --- |
| 1938 | `backend/app/services/orchestration/meeting/engine.py` | Meeting execution engine and result lifecycle. |
| 1129 | `backend/app/services/orchestration/meeting/_prompts.py` | Prompt construction that will need clear separation from product UI guidance. |
| 1090 | `backend/app/services/orchestration/meeting/_prompt_context.py` | Context assembly that should align with command ledger and object refs. |
| 923 | `backend/app/services/orchestration/meeting/_generation.py` | Generation execution path. |
| 813 | `backend/app/services/orchestration/meeting/_session.py` | Meeting session lifecycle and state. |
| 807 | `backend/app/services/orchestration/meeting/dispatch_policy_gate.py` | Dispatch policy gate for execution. |
| 575 | `backend/app/services/orchestration/meeting/_action_items.py` | Action item extraction and governance hooks. |

## P1 Pack Boundary Files

These files live in `mindscape-ai-cloud` and are not the first shell refactor target, but they are the pack-owned boundaries that the shell must call through generic object refs, projections, guidance, command templates, and materializers.

### IG Pack

| Lines | File | Boundary reason |
| ---: | --- | --- |
| 852 | `capabilities/ig/manifest.yaml` | Declares IG object exports, meeting projections, graph projections, tools, and API surface. |
| 957 | `capabilities/ig/ui/modules/ReferencesPanel.tsx` | IG References workbench surface that can invoke AOL selection/workbench actions. |
| 691 | `capabilities/ig/ui/modules/referencesPanel/ReferenceGridCard.tsx` | Current visible card-level AOL entrypoint; includes addressable object action affordance. |
| 788 | `capabilities/ig/ui/modules/referencesPanel/ReferenceDetailModal.tsx` | Owner-detail surface for IG references. |
| 1966 | `capabilities/ig/api/references_api_query_routes.py` | Reference query/detail API surface used by owner resolvers and UI. |
| 875 | `capabilities/ig/services/reference_catalog_read.py` | Reference catalog read path for summaries/detail. |
| 787 | `capabilities/ig/services/reference_catalog_store.py` | Reference storage path. |
| 611 | `capabilities/ig/services/reference_index_read.py` | Reference index read path. |

### Performance Direction Pack

| Lines | File | Boundary reason |
| ---: | --- | --- |
| 1344 | `capabilities/performance_direction/manifest.yaml` | Declares PD object exports, meeting projections, graph projections, guidance playbook, and tool bindings. |
| 2117 | `capabilities/performance_direction/ui/components/PerformanceDirectionStoryboardEditorPage.tsx` | PD workbench surface and storyboard editor that can invoke AOL Runtime Workbench. |
| 1837 | `capabilities/performance_direction/services/object_layer/storyboard_runtime.py` | PD object-layer runtime implementation for storyboard scene/proposal projections and materialization. |
| 557 | `capabilities/performance_direction/services/director_guidance.py` | PD-owned guidance compiler over AOL meeting selections and bounded graph projection. |
| 947 | `capabilities/performance_direction/api/__init__.py` | PD API route module including director guidance compile. |
| 1527 | `capabilities/performance_direction/ui/components/storyboardEditor/StoryboardStrip.tsx` | Large storyboard UI surface; relevant only if shell invocation is embedded there. |
| 675 | `capabilities/performance_direction/ui/components/storyboardEditor/DepartmentCommandEditorPanel.tsx` | Existing command-oriented PD UI; should not bypass AOL command ledger. |
| 535 | `capabilities/performance_direction/ui/components/storyboardEditor/PerformanceDirectionStartSurface.tsx` | PD start surface; possible launch point for AOL Runtime Workbench. |

## Recommended Refactor Tree

Frontend target tree:

```text
web-console/src/components/capabilities/aol-runtime-shell/
  AOLRuntimeShell.tsx
  AOLRuntimeShellProvider.tsx
  AOLRuntimeShellContext.ts
  RuntimeShellPanel.tsx
  RuntimeShellAnchorRail.tsx
  ObjectSelectionPanel.tsx
  ObjectPreviewPanel.tsx
  runtimeShellState.ts
  index.ts

web-console/src/components/capabilities/meeting-workbench/
  MeetingWorkbenchView.tsx
  meetingWorkbenchTypes.ts
  meetingGraphProjection.ts
  meetingCommandImpact.ts
  meetingMentions.ts
  meetingObjectActions.ts
  meetingApi.ts
  MeetingContextBar.tsx
  ObjectOutliner.tsx
  SemanticFlowCanvas.tsx
  PropertiesInspector.tsx
  CommandDock.tsx
  CommandLedger.tsx
  TraceDebugView.tsx
  AOLMeetingBottomShell.tsx
```

Backend target tree:

```text
backend/app/models/object_runtime/
  refs.py
  catalog.py
  selection.py
  actions.py
  meeting.py
  materialization.py
  graph.py
  __init__.py

backend/app/services/object_runtime/
  catalog_service.py
  selection_service.py
  action_planner.py
  action_invoker.py
  materialization_service.py
  graph_projection_service.py
  meeting_attachment_service.py
  __init__.py

backend/app/routes/core/workspace/object_runtime.py

backend/app/models/meeting_graph.py
backend/app/services/meeting_graph/projection_builder.py
backend/app/services/meeting_graph/event_projection.py
backend/app/routes/core/workspace/meeting_graph.py
```

Compatibility rule:

- Keep existing route paths stable.
- Keep old frontend exports stable until capability pages and tests move.
- Add new `AOLRuntimeShell*` names first, then migrate callers.
- Keep `Meeting Graph` as debug/provenance terminology; do not use it as the product title.

## First-Pass Order

1. Extract frontend shell provider/state from `AddressableObjectHostShell.tsx` into `aol-runtime-shell/*`.
2. Add `AOLRuntimeShell` / `AOLRuntimeShellProvider` exports and keep `AddressableObjectHostShell` / `AddressableObjectHostProvider` as compatibility aliases.
3. Extract pure Meeting Workbench projection and mention/object-action helpers from `AOLMeetingBottomShell.tsx`.
4. Extract visual regions from `AOLMeetingBottomShell.tsx`: context/header, canvas, inspector, command dock, debug drawer.
5. Split specs to follow the extracted modules before changing behavior.
6. Split backend object runtime models/services while preserving route contracts.
7. Split meeting graph projection builder from the route.
8. Only after these are stable, begin second-stage UX/UI iteration.

## Refactor Exit Criteria

- `AOLMeetingBottomShell.tsx` becomes a compatibility wrapper and data orchestrator, not a 4000-line product component.
- `AddressableObjectHostShell.tsx` no longer owns all runtime shell concerns directly.
- New work imports `AOLRuntimeShell` / `AOLRuntimeShellProvider`.
- Existing capability pages still work through compatibility exports.
- No endpoint path changes are required for pack compatibility.
- Tests are split by module and still cover the old wrapper path.
