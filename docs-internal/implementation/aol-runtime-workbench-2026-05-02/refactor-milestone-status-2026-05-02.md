# AOL Runtime Shell Refactor Milestone Status - 2026-05-02

Scope: first-stage behavior-preserving refactor plus the first second-stage AOL Runtime Workbench UX/UI productization slice.

## 0. 里程碑口徑修正

本文件後續所有進度只按「計劃級里程碑」驗收，不再把單一拆檔、hook 抽取、component 抽取或 line-count 下降稱為獨立里程碑。

| 層級 | 定義 | 當前狀態 |
| --- | --- | --- |
| 第一階段重構里程碑 | 完成八個 P0 local-core 檔案的相容優先拆分，保持 route path、frontend export、測試契約不破壞，並讓第二階段產品 UX 可以在穩定模組邊界上開展。 | 可關閉；八個 P0 目標與 Object Runtime service shim 均已拆到低於 500 行，route path、model import、frontend legacy export 與 backend monkeypatch contract 均保留。 |
| Command Ledger 產品 gate | 後端 command row 成為 command dock、graph canvas、AOL session feedback 的權威意圖帳本；direct dispatch 只能是 legacy/debug fallback。 | 已有 ledger seed，但 P0 主入口仍未接 `MeetingEngine.run()`；`route_object_action`、`route_playbook`、`route_chat` 目前只能視為 transitional route-owned dispatch，不得宣稱完成 meeting-led orchestration。 |
| AOL 到 MeetingEngine 編排橋接 P0 | AOL command、object refs、graph guidance、relations、pack affordances 必須轉成 `HandoffIn` / `RequestContract`，並由 MeetingEngine 根據任務目的產生 ActionIntent / TaskIR / dispatch / review trace。 | 新增為 blocker；未完成前，IG/PD E2E 只能算 object runtime 與 shell product slice smoke，不能算 meeting-led workflow E2E。計劃文件：`aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md`。 |
| 第二階段 UX/UI 里程碑 | AOL Runtime Workbench 以使用者前端體驗為中心，完成 Context Bar、Object Outliner、Semantic Flow Canvas、Inspector、Command Dock/Ledger 的可產品化布局與交互閉環。 | UI product slice 已落地多個前端體驗面，但收尾驗收必須等待 AOL 到 MeetingEngine 編排橋接 P0；否則只能證明 shell/ledger/projection/materializer 工作，不能證明最初設計的 meeting-guided workflow。 |
| Checkpoint | 單一拆檔、hook/component/service extraction、spec split、line gate 更新。 | 只能作為里程碑內部證據，不得單獨當成里程碑。 |

## 1. Problem list

1. **Frontend shell rename is now dependency-direction correct**: `AOL Runtime Shell` owns the runtime shell entry, provider implementation, panel UI, and state helpers; legacy `AddressableObjectHostShell` is now only a compatibility facade. Evidence: E1, E2, E4. Severity: 3. Detection: 5. Priority: 15.
2. **`AOLMeetingBottomShell.tsx` is now a wrapper-level Meeting Workbench shell**: data/runtime loading, command submit orchestration, graph projection, canvas, command dock, inspector, and context popovers have been moved behind smaller modules while preserving the current UI contract. Evidence: E2. Severity: 2. Detection: 5. Priority: 10.
3. **Extracted Meeting Workbench helpers now have direct tests**: graph projection, mention parsing, object action plan/invoke payloads, and AOL session context conversion no longer rely only on the monolithic shell spec. Evidence: E3. Severity: 4. Detection: 5. Priority: 20.
4. **AOL Runtime Shell and Meeting Workbench shell specs now follow the new ownership**: legacy facade specs only validate compatibility; runtime shell behavior moved to `aol-runtime-shell` specs, and Meeting Workbench UI behavior moved to layout, mentions, and dispatch specs. Evidence: E3. Severity: 3. Detection: 5. Priority: 15.
5. **Command submit now writes the ledger first, and runtime dispatch/status is route-owned for the main P0 paths**: local-core now has `MeetingCommandEnvelope`, server-side command parsing, a Postgres-backed command store, workspace-scoped command routes, execution-graph command-ledger projection, and frontend command submit now posts to `/meetings/{meeting_id}/commands` first. The command route owns role-bearing object-action plan/invoke, selected pack-tool `execute_playbook`, and ordinary chat/runtime background dispatch. Task-backed work now syncs command rows from accepted/running into completed/failed through `TasksStore`, and chat-only background dispatch marks the command completed/failed when the chat service returns. Execution-graph command ledger nodes now map durable command lifecycle states into UI graph states, and Meeting Workbench subscribes to the shared workspace SSE stream so runtime/artifact/session events for the active meeting refresh graph, events, and artifacts. The frontend no longer has a direct `/chat` or local object-action compatibility fallback for command submit; missing `dispatch_result` is treated as a backend contract error. Evidence: E5, E6, E7. Severity: 5. Detection: 5. Priority: 25.

## 2. Evidence

E1. New shell module exists under `web-console/src/components/capabilities/aol-runtime-shell/`, and `web-console/src/components/capabilities/AddressableObjectHostShell.tsx` only re-exports legacy compatibility names.

E2. Current line counts after this milestone:

- `web-console/src/components/capabilities/AddressableObjectHostShell.tsx`: 17 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShell.tsx`: 114 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellAttachFlow.spec.tsx`: 468 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProviderImpl.tsx`: 90 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProvider.spec.tsx`: 38 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellSurfaces.spec.tsx`: 324 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/RuntimeObjectPanel.tsx`: 324 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/RuntimeObjectPreview.tsx`: 293 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AddressableObjectPanel.tsx`: 4 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/AddressableObjectPreview.tsx`: 4 lines.
- `web-console/src/components/capabilities/aol-runtime-shell/runtimeShellState.ts`: 152 lines.
- `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx`: 38 lines.
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`: 472 lines.
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx`: 31 lines.
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellLayout.spec.tsx`: 325 lines.
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellMentions.spec.tsx`: 183 lines.
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx`: 310 lines.
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellPackFixtures.spec.tsx`: 151 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchTestData.ts`: 246 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchTestHarness.ts`: 376 lines.
- `web-console/src/components/capabilities/meeting-workbench/useMeetingWorkbenchData.ts`: 180 lines.
- `web-console/src/components/capabilities/meeting-workbench/useMeetingThreadData.ts`: 430 lines.
- `web-console/src/components/capabilities/meeting-workbench/useMeetingObjectContextData.ts`: 148 lines.
- `web-console/src/components/capabilities/meeting-workbench/useMeetingObjectRegistryMentions.ts`: 119 lines.
- `web-console/src/components/capabilities/meeting-workbench/useMeetingPackTools.ts`: 114 lines.
- `web-console/src/components/capabilities/meeting-workbench/useRuntimeInspectorSnapshot.ts`: 100 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingCommandSubmit.ts`: 326 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchStatus.ts`: 27 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchStatus.spec.ts`: 56 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphProjection.ts`: 400 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingCommandImpact.ts`: 128 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphFormatting.ts`: 65 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphObjectProjection.ts`: 150 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphParsing.ts`: 104 lines.
- `web-console/src/components/capabilities/meeting-workbench/SemanticFlowCanvas.tsx`: 397 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingGraphNodeCard.tsx`: 103 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingLaneBoard.tsx`: 82 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingWorkSubgraphCanvas.tsx`: 185 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingWorkbenchStage.tsx`: 70 lines.
- `web-console/src/components/capabilities/meeting-workbench/CommandLedgerStrip.tsx`: 75 lines.
- `web-console/src/components/capabilities/meeting-workbench/ObjectOutlinerPanel.tsx`: 316 lines.
- `web-console/src/components/capabilities/meeting-workbench/CommandDock.tsx`: 212 lines.
- `web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx`: 238 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingWorkInspectorPanel.tsx`: 302 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingRuntimeInspectorPanel.tsx`: 102 lines.
- `web-console/src/components/capabilities/meeting-workbench/MeetingContextPanels.tsx`: 330 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingMentions.ts`: 304 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingObjectActions.ts`: 100 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingSessionContext.ts`: 198 lines.

E3. Focused specs added:

- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellAttachFlow.spec.tsx`
- `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellSurfaces.spec.tsx`
- `web-console/src/components/capabilities/meeting-workbench/meetingMentions.spec.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingObjectActions.spec.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingSessionContext.spec.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphProjection.spec.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchStatus.spec.ts`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellLayout.spec.tsx`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellMentions.spec.tsx`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx`

E4. App callers migrated to the new `aol-runtime-shell` exports:

- `web-console/src/app/workspaces/[workspaceId]/layout.tsx`
- `web-console/src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.tsx`
- `web-console/src/app/workspaces/[workspaceId]/capabilities/performance_direction/PerformanceDirectionWorkbenchHost.tsx`

E5. The command-ledger gate remains as defined in `docs-internal/implementation/aol-runtime-workbench-2026-05-02/meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md`.

E6. Backend command-envelope seed added in this milestone:

- `backend/app/models/meeting_command.py`: 112 lines.
- `backend/app/services/meeting_command_parser.py`: 200 lines.
- `backend/app/services/meeting_command_dispatch.py`: 363 lines.
- `backend/app/services/meeting_command_status_sync.py`: 158 lines.
- `backend/app/services/meeting_execution_graph_commands.py`: 125 lines.
- `backend/app/services/stores/meeting_command_store.py`: 211 lines.
- `backend/app/routes/core/workspace/meeting_commands.py`: 263 lines.
- `backend/features/workspace/chat/__init__.py`: 19 lines; lazy router export prevents route/service circular imports when command routes reuse chat orchestration services.
- `backend/tests/test_meeting_command_parser.py`: 68 lines.
- `backend/tests/test_meeting_command_envelope.py`: 405 lines.
- `backend/tests/test_meeting_execution_graph_commands.py`: 182 lines.
- `backend/tests/test_meeting_command_status_sync.py`: 103 lines.

E7. Frontend command-ledger submit bridge added in this milestone:

- `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.ts`: 110 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.spec.ts`: 33 lines.
- `web-console/src/components/capabilities/meeting-workbench/meetingCommandSubmit.ts`: command submit now writes a server command row first, consumes route-owned object-action, object-action-plan, playbook, or chat dispatch results, and treats missing dispatch evidence as a backend contract error.
- `web-console/src/components/capabilities/meeting-workbench/meetingObjectActions.ts`: object-action plan/invoke request context now carries `command_id`.
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphParsing.ts`: lifecycle statuses from durable command rows are normalized into graph UI statuses instead of dropping command nodes.
- `web-console/src/components/capabilities/meeting-workbench/useMeetingThreadData.ts`: Meeting Workbench subscribes to the shared workspace event stream and refreshes graph/events/artifacts for active meeting runtime events.

## 3. Completed changes

### Change 1: Introduced AOL Runtime Shell compatibility layer and corrected dependency direction

- Added `AOLRuntimeShell`, `AOLRuntimeShellProvider`, shell context, provider implementation, panel, rail, and anchor modules under `aol-runtime-shell/`.
- Moved the runtime provider/controller implementation into `AOLRuntimeShellProviderImpl.tsx`.
- Moved object targeting panel UI into `AddressableObjectPanel.tsx`.
- Moved pure runtime shell state helpers into `runtimeShellState.ts`.
- Kept legacy `AddressableObjectHostShell` exports as a 17-line compatibility facade for current tests and callers.
- Updated IG/PD capability hosts and workspace layout to consume the new shell exports.

### Change 2: Extracted Meeting Workbench helper boundaries

- Added `meetingWorkbenchTypes.ts`, `meetingWorkbenchConstants.ts`, and `meetingWorkbenchUtils.ts`.
- Added `meetingApi.ts` with behavior-preserving API URL fallback semantics.
- Added `meetingMentions.ts` for mention query, token insertion, registry conversion, raw-token parsing, and object-action entry role mapping.
- Added `meetingObjectActions.ts` for plan/invoke payload construction and planned-payload detection.
- Added `meetingSessionContext.ts` for AOL session metadata to object summary, selection, attach response, title, and search corpus conversion.
- Added `meetingGraphProjection.ts` for event/artifact projection and final semantic graph assembly.
- Added `meetingGraphParsing.ts`, `meetingGraphObjectProjection.ts`, `meetingGraphFormatting.ts`, and `meetingCommandImpact.ts` so execution graph coercion, object graph refs/nodes, formatting, and command impact are separately testable boundaries.
- Added `SemanticFlowCanvas.tsx` for the header toolbar and graph canvas pan/zoom/highlight UI.
- Added `CommandDock.tsx` for pack tool selection, command input, mention picker, and command submit affordance.
- Added `PropertiesInspector.tsx` for inspector rail, runtime/session/trace/graph/prompt/patch panels, and console drawer.
- Added `MeetingRuntimeInspectorPanel.tsx` for runtime binding details.
- Added `MeetingContextPanels.tsx` for object context and meeting session popovers.

### Change 3: Extracted Meeting Workbench orchestration hooks/controllers

- Added `useMeetingWorkbenchData.ts` as the composition hook for meeting thread data, object context, pack tools, registry mentions, and runtime inspector state.
- Added `useMeetingThreadData.ts` for meeting session list, active session, event replay, execution graph, and artifact loading.
- Added `useMeetingObjectContextData.ts` for AOL session/object summary fallback and bounded object graph projection.
- Added `useMeetingObjectRegistryMentions.ts` for object registry sync and `@object` completion.
- Added `useMeetingPackTools.ts` for pack playbook discovery.
- Added `useRuntimeInspectorSnapshot.ts` for inspector-scoped runtime state reads.
- Added `meetingCommandSubmit.ts` for command submit orchestration, including `@pack` reference resolution, command-ledger acceptance, and route-owned dispatch handling.

### Change 4: Added focused tests for extracted boundaries

- `meetingMentions.spec.ts` covers trailing mention query, token apply, registry item conversion, raw pack/node parsing, and object action entries.
- `meetingObjectActions.spec.ts` covers plan skip, plan payload, rejected plan payload, planned-payload detection, and invoke payload.
- `meetingSessionContext.spec.ts` covers AOL metadata read, object summary, selection, attach response, display title, and search corpus.
- `meetingGraphProjection.spec.ts` covers execution graph coercion, graph refs, object graph nodes, semantic lane projection, and command impact.
- `AOLRuntimeShellSurfaces.spec.tsx` covers shared anchors, existing meeting session opening, and object replacement across surfaces.
- `AOLRuntimeShellAttachFlow.spec.tsx` covers selected, attaching, and meeting-opened state reuse, generic context roles, and ambiguous candidate attach flow.
- `AddressableObjectHostShell.spec.tsx` now only covers legacy facade compatibility.
- `AOLMeetingBottomShellLayout.spec.tsx` covers graph-first shell layout, execution graph rendering, object graph projection, session filtering/selection, inspector exclusivity, zoom, and pan.
- `AOLMeetingBottomShellMentions.spec.tsx` covers `@pack` insertion, registry-backed storyboard/storyboard-scene/character completions, object completion replacement, and structured reference dispatch.
- `AOLMeetingBottomShellDispatch.spec.tsx` covers unresolved raw mention safety, session switching, route-owned chat dispatch, missing dispatch-result contract errors, scoped console opening, and pack tool dispatch.
- `AOLMeetingBottomShell.spec.tsx` now only covers legacy spec entrypoint compatibility.
- `meetingWorkbenchTestData.ts` and `meetingWorkbenchTestHarness.ts` centralize shared shell fixtures and API mocks for the focused specs.

### Change 5: Added backend command-envelope contract seed

- Added `MeetingCommandEnvelope`, `MeetingRequestedAction`, `MeetingCommandRecord`, accepted response, and list response models.
- Added server-side P0 command grammar normalization for free text, slash verbs, `@owner.kind:id` object refs, and small role hints.
- Added `MeetingCommandStore` with a dedicated `meeting_commands` table and indexes for `(workspace_id, meeting_id)`, `(workspace_id, thread_id)`, and client draft lookup.
- Added `POST /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands` and `GET /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands`.
- Added command-ledger projection into `meeting_graph.py` so graph command nodes can prefer durable `command_id` rows.
- Kept runtime dispatch integration marked as `pending_runtime_integration`; this preserves the current compatibility path until frontend submit routing is migrated.

### Change 6: Routed frontend command submit through command ledger first

- Added `meetingCommandLedger.ts` to submit a `MeetingCommandEnvelope` from the command dock.
- Sanitized legacy UI mention tokens before sending `intent_text` to the server parser, while preserving the raw command in command metadata.
- Updated `meetingCommandSubmit.ts` so command dock submit first receives a durable `command_id`, then consumes route-owned object-action, object-action-plan, playbook, or chat dispatch results.
- Updated object-action request context so graph projection can join runtime tasks back to the durable command ledger node.
- Updated shell dispatch tests to assert command route writes happen before runtime compatibility dispatch.

### Change 7: Made role-bearing object-action commands route-owned

- Added optional `dispatch_result` to command submit responses.
- Added explicit `metadata.dispatch_mode = route_object_action` for frontend commands with two or more role-bearing object refs and no selected pack tool.
- Updated the command route to plan and invoke object actions when `dispatch_mode` is `route_object_action`.
- Updated command records to `running`, `completed`, or `failed` during route-owned object-action dispatch.
- Updated frontend submit handling so route-owned object-action results stop local compatibility plan/invoke.
- Removed frontend fallback to local object-action plan/invoke and direct `/chat`; command submit now requires route-owned dispatch evidence.

### Change 8: Made selected pack-tool/playbook commands route-owned

- Added explicit `metadata.dispatch_mode = route_playbook` for frontend commands with a selected pack tool.
- Added requested action parameters to the command envelope so the route receives the same meeting/session/object context that the old chat dispatch used.
- Updated the command route to call the existing orchestrator `handle_suggestion_action(action="execute_playbook")` path for selected pack tools.
- Updated command records to move through `running` and back to `accepted` or `failed`, with `accepted_task_id` populated from the playbook execution result when available.
- Updated frontend submit handling so route-owned playbook results stop local `/chat` compatibility dispatch.
- Updated dispatch tests to assert selected pack tool submissions write `/commands` and do not call `/chat`.

### Change 9: Made ordinary chat/runtime commands route-owned

- Added explicit `metadata.dispatch_mode = route_chat` for command submissions that are not selected pack tools and do not have enough role-bearing refs for object-action dispatch.
- Added command action parameters into command metadata so the route has the same selected object, meeting, thread, and mention context that the old frontend `/chat` call used.
- Updated the command route to create a `WorkspaceChatRequest` and schedule `ChatOrchestratorService.run_background_chat` through FastAPI background tasks.
- Used the durable `command_id` as the accepted runtime event pointer for route-owned chat dispatch, keeping graph/session joins command-ledger-first.
- Updated frontend submit handling so route-owned chat results stop local `/chat` compatibility dispatch.
- Changed `backend/features/workspace/chat/__init__.py` to lazily export `router`, preventing circular imports when lower-level chat services import `chat.streaming.*`.
- Updated dispatch tests to assert ordinary meeting commands write `/commands` with `route_chat` and do not call `/chat`.

### Change 10: Added command-ledger status sync from runtime completion

- Added `meeting_command_status_sync.py` to extract `command_id` from task params/results/execution context and map task statuses into command statuses.
- Wired `TasksStore.create_task`, `update_task_status`, and `update_task` to best-effort sync command rows without letting ledger sync failures break task persistence.
- Added runtime task metadata under command rows so the ledger records task id, execution id, pack id, task type, completion timestamp, and error.
- Wrapped route-owned chat background dispatch so chat-only commands can become `completed` or `failed` even when no execution task is produced.
- Extracted route dispatch implementation into `meeting_command_dispatch.py`, reducing `meeting_commands.py` from 547 lines to 263 lines.
- Added focused backend tests for command id extraction, task-status mapping, and command-row sync.

### Change 11: Removed frontend command-submit compatibility fallback

- Removed `useSendMessage` from `AOLMeetingBottomShell`; command dispatch loading is now local to the command route submit flow.
- Removed the `sendMessage` dependency and fallback path from `meetingCommandSubmit.ts`.
- Removed frontend direct calls to `/object-actions/plan`, `/object-actions/invoke`, and `/chat` from command submit; those paths remain covered by their own helper tests but are no longer command-submit fallbacks.
- Added handling for route-owned `object_action_plan` responses that do not produce an invocation, so rejected or not-planned object actions render as command results instead of retrying locally.
- Treat missing route-owned dispatch evidence as a backend contract error.
- Added dispatch regression coverage proving a missing `dispatch_result` does not trigger `/chat`, `/object-actions/plan`, or `/object-actions/invoke`.

### Change 12: Made command-ledger graph visibility runtime-refreshed

- Mapped durable command lifecycle states (`drafted`, `accepted`, `running`, `completed`, `failed`, `superseded`) into the graph UI status vocabulary (`pending`, `running`, `ready`, `error`, `blocked`) during backend command-ledger projection.
- Preserved raw durable lifecycle state in command node metadata as `ledger_status`.
- Added defensive frontend status normalization so command nodes are still visible if lifecycle statuses arrive directly from an execution graph payload.
- Subscribed `useMeetingThreadData` to the shared workspace SSE event stream for active meeting/session events.
- Runtime, artifact, and session events now trigger execution graph, event replay, and artifact refresh for the active Meeting Workbench surface without depending on a separate chat component to forward DOM events.
- Added frontend regression coverage that lifecycle-status command nodes are rendered and command submit causes execution graph refresh.

### Change 13: Started product Work-view UX on top of the command-ledger spine

- Changed the default graph view from internal `flow` to product-facing `Work`.
- Kept `Runs` and `Trace` as secondary/debug views.
- Replaced default Work-view lane labels with product semantics: `Focus`, `Guidance`, `Command Ledger`, `Runtime`, `Outcomes`, `Assets`, and `Next`.
- Replaced Work-view header debug counters/raw session id with context chips for focus object, work status, runtime binding, and next step.
- Added a Work-view `CommandLedgerStrip` so command-ledger entries are selectable without opening raw Trace first.
- Added `MeetingWorkbenchStage.tsx` to host the Work-view editor region.
- Moved `ObjectOutlinerPanel` out of the canvas overlay and into the Work-view left editor column, while keeping it on the same selection state as the canvas and inspector.
- Moved `CommandLedgerStrip` out of the canvas overlay and into a dedicated bottom editor band owned by `MeetingWorkbenchStage`.
- Moved the inspector rail/panel placement into a right-side `MeetingWorkbenchStage` editor slot, so the shell wrapper no longer owns the inspector as an external sibling of the workbench.
- Added Work-view inspector labels for product task semantics: `Summary`, `Guidance`, `Actions`, `Context`, `Runtime`, `Review`, and `Trace`, while preserving existing tab ids and Trace/debug fallback compatibility.
- Kept node/trace counts and raw active meeting id in non-Work views only.
- Added `meetingWorkbenchStatus.ts` so work status, runtime label, and next-step text are derived outside the shell wrapper.
- Added regression assertions that Work view is the default, the stage exists, the stage owns separate main-editor, right-inspector, and bottom-ledger regions, command-ledger lane wording is product-facing, the ledger strip can select command impact, the object outliner can select the focus object, guidance/relations lane wording is product-facing, raw debug counters do not lead the default Work view, and loading placeholders do not masquerade as runtime execution.

### Change 14: Replaced default Work-view lane board with a selected-subgraph canvas

- Added `MeetingGraphNodeCard.tsx` as the shared graph node card renderer so Work, Runs, and Trace views use the same node ids, selection state, command badges, and command-impact highlighting.
- Added `MeetingLaneBoard.tsx` to preserve the legacy fixed lane board for non-Work debug views.
- Added `MeetingWorkSubgraphCanvas.tsx` for the default Work view, rendering the user-facing work sequence as `Focus -> Guidance -> Command -> Runtime -> Outcome -> Next`.
- Work view no longer renders `meeting-graph-lanes`; fixed lane categories remain available behind secondary/debug graph modes.
- Command selection, ledger-strip selection, canvas pan/zoom, inspector opening, command impact highlighting, and object outliner selection continue to share the same `selectedNodeId` path.
- Updated regression coverage so Work view asserts the selected-subgraph canvas and work-step regions instead of the fixed lane board.

### Change 15: Added task-oriented Work-view inspector content

- Added `MeetingWorkInspectorPanel.tsx` for Work-view `Summary`, `Guidance`, `Actions`, `Context`, `Runtime`, and `Review` content.
- Work-view `Guidance` now renders product-facing context relations instead of the legacy `Bounded object graph` debug panel.
- Work-view `Actions` summarizes command impact counts and selected command focus without opening raw trace.
- Work-view `Summary` centers the selected graph node plus focus object identity, instead of only showing the attached object summary.
- Work-view `Context` keeps meeting/workspace/focus references visible without exposing API internals.
- The `Trace` tab still uses the raw replay/JSON panel, and non-Work views keep the legacy inspector content path.
- Updated regression coverage to assert the Work-view guidance panel, while existing runtime/session/trace checks still pass.

### Change 16: Added explicit provenance path and dense-session caps to Work subgraph

- Passed execution graph edges into `MeetingWorkbenchStage`, `MeetingTaskCanvas`, and `MeetingWorkSubgraphCanvas`.
- Added a Work-view `Provenance path` strip that renders visible runtime proof as `source -> edge type -> target` chips.
- When a command is selected, the provenance strip is scoped to that command's `commandImpact.edgeIds`; otherwise it shows visible meeting-flow edges.
- Added per-step Work-view node caps so dense sessions stay product-readable and overflow is summarized as hidden signals instead of expanding into a debug board.
- Added regression coverage for the `produced` provenance edge from runtime closure to output object.

### Change 17: Aligned Workbench product UI labels with i18n

- Added Workbench-specific i18n keys for the Work-view header, task canvas, object outliner, command ledger, provenance strip, and Work inspector content.
- Added English, Traditional Chinese, and Japanese locale entries for those keys.
- Passed the shared translation function from `AOLMeetingBottomShell` into `MeetingHeaderToolbar`, `MeetingWorkbenchStage`, `MeetingTaskCanvas`, `MeetingWorkSubgraphCanvas`, `ObjectOutlinerPanel`, `CommandLedgerStrip`, `MeetingInspectorRail`, and `MeetingInspectorPanel`.
- Updated Work-view layout assertions so structural/product behavior is tested through stable regions and graph data, not hard-coded English UI copy.
- Current first-stage large-file status after this milestone: `AOLMeetingBottomShell.tsx` is 498 lines and `PropertiesInspector.tsx` is 495 lines.

### Change 18: Renamed the runtime rail entry from Workbench to Flow

- Changed the global AOL Runtime Shell right rail entry label from `Workbench` to `Flow`, so it no longer collides with pack-owned workbench surfaces such as IG Workbench or PD Workbench.
- Added `RuntimeFlowAnchor.tsx` as the product-facing rail anchor component.
- Kept `RuntimeWorkbenchAnchor.tsx` as a compatibility re-export for older imports while the broader rename plan proceeds.
- Updated rail tooltip and accessibility labels to `Runtime Flow`.
- Added i18n keys and English, Traditional Chinese, and Japanese locale values for the runtime shell rail labels.
- Renamed rail test ids from `aol-graph-shell-*` to `aol-runtime-flow-*`.

### Change 19: 新增中性的 pack guidance projection contract

- 在 `ObjectGraphProjection` 新增 `guidance` 欄位，並以 `ObjectGuidanceCard` 表達 pack 投影出的下一步引導卡。
- `/object-graph/project` 只負責正規化 owner pack 回傳的 `guidance` 資料，不在 local-core 寫入 IG/PD 專屬業務規則。
- Guidance card 支援 `title`、`description`、`intent`、`command_template`、`priority` 與保留式 `metadata`，讓 pack 可以投影「下一步應做什麼」與「可插入 command 的模板」。
- Work view 的 Guidance step 會把 object graph projection 中的 guidance card 顯示為可讀節點；Inspector 的 Guidance 面板會同時呈現 guidance card 與 bounded relations。
- Guidance node 現在會把 `command_template` 放入 node metadata；使用者選中 guidance node 且 command draft 為空時，CommandDock 會自動帶入該模板，仍由單一 command ledger 送出，不新增分散式 action button。
- 測試 harness 新增 `Director framing` guidance card，驗證 pack-projected guidance 能從 `/object-graph/project` 進入 Work canvas 與 inspector。
- Guidance command draft 邏輯抽到 `meetingGuidanceCommand.ts`，避免讓 `AOLMeetingBottomShell.tsx` 回到 500 行以上。
- 這一層 contract 對齊原始設計目標：meeting graph node 不是 generic graph viewer，而是把使用者意圖、物件引用、pack guidance、command template、runtime execution 與資產結果接成可追溯協作脊椎。

### Change 20: 補齊 guidance review/proposal affordance 閉環

- `ObjectGuidanceCard` 新增 `review_label`、`review_routes`、`proposal_ref`、`target_ref`，讓 owner pack 可以投影可審查提案、審查入口與目標物件。
- `/object-graph/project` 會從 pack projection 正規化 `review_route` / `review_routes`，並解析 `proposal_ref` / `target_ref`，但仍不在 local-core 寫入 IG/PD 專屬判斷。
- Frontend `ObjectGuidanceCard` 型別同步新增 review/proposal 欄位。
- `meetingGraphObjectProjection.ts` 會把 review/proposal affordance 放入 guidance node metadata，並提供 `collectObjectGuidanceReviewAffordances` 供 Review inspector 聚合。
- Work view Guidance inspector 會在 guidance card 內顯示 command template、review route、proposal ref、target ref。
- Work view Review inspector 現在同時顯示 attach response 的 review routes 與 guidance-projected review routes，讓使用者可從 AI guidance 直接進入 review/proposal 路由。
- 測試 harness 新增 `Review shot proposal`、`storyboard_proposal` 與 review route fixture；layout test 覆蓋 Guidance inspector 與 Review inspector 的可見閉環。

### Change 21: 補齊密集 provenance path 的 overflow grouping

- `MeetingWorkSubgraphCanvas` 不再直接把 visible provenance edges 截斷成 6 條後丟棄剩餘證據。
- 新增 relevant provenance edge 集合：一般 Work flow 依 visible nodes 篩選，選中 command 時仍依 `commandImpact.edgeIds` 篩選。
- 前 6 條 proof edges 保持水平 chips；超出的 proof edges 會進入 `meeting-work-provenance-overflow` 可展開 group。
- Overflow group 顯示剩餘證據邊數，展開後列出每條 hidden proof edge 的 source、edge label/type、target，讓密集 session 保持可掃描但不丟 runtime proof。
- 新增 `meetingWorkbenchMoreProofEdges`、`meetingWorkbenchHiddenProofEdges` i18n keys，並補 English、繁體中文、日文語系。
- 新增 layout regression test：8 條 provenance edges 時，前 6 條作為主 path 呈現，後 2 條出現在 overflow group。

### Change 22: 明確化 command-ledger 本地刷新事件，暫不新增 dedicated SSE stream

- 盤點結果：目前 Meeting Workbench 已透過 shared workspace SSE、`workspace-chat-updated`、`workspace-task-updated`、route-owned dispatch result 和 optimistic `localTasks` 更新 Work view。
- 判斷：當前缺口不是需要新增後端 dedicated command-ledger stream，而是 command ledger 在前端缺少語義明確的本地刷新事件。
- 新增 `meetingCommandEvents.ts`，定義 `meeting-command-ledger-updated` browser event 與 workspace/meeting/command/status detail。
- `meetingCommandSubmit.ts` 在 `/commands` route 接受 durable command 後立即 dispatch `meeting-command-ledger-updated`，讓 execution graph 可以在 route-owned dispatch 後續 runtime events 抵達前先刷新一次。
- `useMeetingThreadData.ts` 監聽 `meeting-command-ledger-updated`，只在 workspace id 與 active meeting id 對上時重抓 execution graph、meeting events、artifacts。
- 保留既有 shared workspace SSE 與 `workspace-task-updated` 相容路徑，避免為本地 UX latency 新增後端 stream 或改動 runtime 邊界。
- Dispatch regression 新增兩個驗證：提交 command 後會發出 `meeting-command-ledger-updated`；active meeting 收到該事件會重抓 execution graph。

### Change 23: 收斂 AOL Runtime Shell 主路徑命名，保留 legacy 相容出口

- `AOLRuntimeShellProviderImpl.tsx` 的主實作引用改用 `AOLRuntimeShellContext`、`IDLE_RUNTIME_SHELL_STATE`、`AOLRuntimeShellController`、`AOLRuntimeShellProviderProps`、`AOLRuntimeShellState`、`AOLRuntimeSurfaceContext` 與 `RegisteredRuntimeSurfaceContext`。
- Provider 主出口改為 `AOLRuntimeShellProviderImpl`，`AddressableObjectHostProvider` 只保留為 legacy alias，避免 pack 或舊測試一次性斷裂。
- Object panel 主實作檔改為 `RuntimeObjectPanel.tsx`，原 `AddressableObjectPanel.tsx` 只保留薄 re-export。
- Object preview 主實作檔改為 `RuntimeObjectPreview.tsx`，原 `AddressableObjectPreview.tsx` 只保留薄 re-export。
- `runtimeShellState.ts`、`RuntimeShellToolRail.tsx`、`RuntimeFlowAnchor.tsx`、`RuntimeObjectSelectionAnchor.tsx` 與 `RuntimeShellPanel.tsx` 的 state/surface type 改用正式 runtime shell 型別。
- `aol-runtime-shell/index.ts` 新增 `RuntimeObjectPanel` 與 `RuntimeObjectSourcePreview` 主出口，同時保留 `AddressableObjectPanel` 與 `AddressableObjectSourcePreview` 相容出口。
- Runtime shell regression 新增 alias 斷言，確認 `AddressableObject*` legacy export 與 `RuntimeObject*` 主 export 指向同一實作。

### Checkpoint 24: 拆分 AOL Runtime Shell provider 的 controller 與 pane sizing 責任

- `AOLRuntimeShellProviderImpl.tsx` 從 498 行降到 90 行，只保留 provider composition、runtime object panel、tool rail 與 meeting pane 的掛載。
- 新增 `useAOLRuntimeShellHostController.ts`，集中管理 surface registry、object resolve、candidate selection、meeting attach、runtime flow open 與 context controller memo。
- 新增 `useRuntimeShellMeetingPaneSizing.ts`，集中管理 meeting pane height、drag resize、preset sizing 與 resize clamp。
- 保留 `AOLRuntimeShellProviderImpl` 與 `AddressableObjectHostProvider` legacy alias，不更動 pack 呼叫端契約。
- 將 React pointer event 與 DOM pointer event 型別分開，避免 window listener 型別被 React event shadow。
- Runtime shell regression 維持 4 files / 9 tests passed；Meeting Workbench regression 維持 10 files / 43 tests passed。

### Checkpoint 25: 拆分 Meeting Inspector default content，解除 PropertiesInspector 大檔風險

- `PropertiesInspector.tsx` 從 495 行降到 238 行，只保留 inspector rail、panel shell、Work/default content routing 與 console drawer。
- 新增 `MeetingDefaultInspectorContent.tsx`，集中非 Work view 的 object/session/trace/graph/prompts/review inspector content。
- Work view 仍由既有 `MeetingWorkInspectorContent` 負責；runtime view 仍透過 `MeetingRuntimeInspectorContent` 顯示，不改變使用者可見行為。
- Trace filter、selected trace event、bounded object graph projection render 邏輯移入 default content component，讓第二階段 UX 加面板時不再直接推高 `PropertiesInspector.tsx`。
- Meeting Workbench regression 維持 10 files / 43 tests passed；AOL Runtime Shell regression 維持 4 files / 9 tests passed；backend command tests 維持 15 passed。

### Checkpoint 26: 拆分 Meeting mention aggregation，解除 AOLMeetingBottomShell 大檔風險

- `AOLMeetingBottomShell.tsx` 從 498 行降到 378 行，保留 shell state、graph projection、event handlers 與 layout composition。
- 新增 `useMeetingMentionItems.ts`，集中 session/object/applied registry/pack/node mention item aggregation。
- Mention token、structured reference、dedupe 行為保持不變，仍由 command dock 透過同一 `mentionItems` contract 使用。
- `AOLMeetingBottomShell.tsx` 不再直接依賴 `createMentionReference` 或 `shortId`，減少 shell 對 mention projection 細節的耦合。
- Meeting Workbench regression 維持 10 files / 43 tests passed；AOL Runtime Shell regression 維持 4 files / 9 tests passed；backend command tests 維持 15 passed。

### Checkpoint 27: 拆分 AOL Runtime Shell surface registry

- `useAOLRuntimeShellHostController.ts` 從 435 行降到 393 行，保留 object targeting、selection resolve、meeting attach、runtime flow open 與 controller memo。
- 新增 `useAOLRuntimeSurfaceRegistry.ts`，集中 `activateSurface` / `deactivateSurface`、registered surface stack、active surface fallback 邏輯。
- Surface registry hook 透過 `setPanelState` 更新 active surface，不改變 `AOLRuntimeShellController` 對外 contract。
- `AOLRuntimeShell.tsx` 仍透過 controller 的 `activateSurface` / `deactivateSurface` 註冊 mounted pack surfaces；legacy host facade 保持相容。
- AOL Runtime Shell regression 維持 4 files / 9 tests passed；Meeting Workbench regression 維持 10 files / 43 tests passed；backend command tests 維持 15 passed。

### Checkpoint 28: 拆分 legacy Meeting Records route，避免與 Meeting Workbench shell 混名

- `web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx` 從 760 行降到 132 行，保留 route path 與 `project_id`、`session_id`、`open_patch` query 行為。
- 新增 `meetingRecords.types.ts`、`meetingRecordsApi.ts`、`meetingRecordsUtils.ts`、`MeetingRecordsHeader.tsx`、`MeetingSessionCard.tsx`、`MeetingSessionList.tsx`、`MeetingSessionDetailPanel.tsx`。
- Route component 名稱固定為 `MeetingRecordsPage`，可見 copy 保持 `Meeting Records`，避免把這個歷史紀錄/admin route 誤認為 AOL Runtime Workbench shell。

### Checkpoint 29: 拆分 Meeting Graph route projection

- `backend/app/routes/core/workspace/meeting_graph.py` 從 950 行降到 137 行，只保留 route、bounded lookup 與相容 export。
- 新增 `backend/app/models/meeting_graph.py`，集中 `MeetingExecutionGraphNode`、`MeetingExecutionGraphEdge`、`MeetingExecutionGraphResponse`。
- 新增 `backend/app/services/meeting_graph/projection_builder.py`、`projection_utils.py`、`task_projection.py`、`event_projection.py`，且每個新檔低於 500 行。
- 保留 `build_meeting_execution_graph` 與 `merge_meeting_event_runtime_projection` 在 route module 的相容 export。

### Checkpoint 30: 將 Object Runtime models 轉成相容 package

- `backend/app/models/object_runtime.py` 已轉成 `backend/app/models/object_runtime/` package，`__init__.py` 保留原本 `from backend.app.models.object_runtime import ...` 相容 contract。
- 模型按 refs、catalog、instance_index、selection、meeting、materialization、actions、graph 拆分；各新檔均低於 500 行。
- `.gitignore` 增列 `!/backend/app/models/object_runtime/`，修正 repo 既有 `/backend/app/models/*/` ignore 規則會漏掉新 package 的問題。

### Checkpoint 31: 將 Object Runtime route 降為相容 facade

- `backend/app/routes/core/workspace/object_runtime.py` 從 2874 行降到 366 行，保留所有 endpoint path 與 public route function 名稱。
- 新增 `backend/app/services/object_runtime/route_services.py` 作為相容優先的 service shim，route facade 在每次 wrapper 執行前同步 private helper aliases，保留現有動態 import 測試與 monkeypatch 行為。
- 此 checkpoint 只關閉 route facade；service 內部分層由 Checkpoint 32 關閉。

### Checkpoint 32: 拆分 Object Runtime service shim

- `backend/app/services/object_runtime/route_services.py` 從 2874 行相容 shim 降到 142 行，只保留 compatibility facade、helper alias 同步與 endpoint delegation。
- 新增 `dependencies.py`、`common.py`、`summary_service.py`、`catalog_service.py`、`action_helpers.py`、`action_service.py`、`selection_service.py`、`meeting_projection.py`、`materialization_service.py`、`meeting_attach_service.py`、`graph_service.py`，各檔均低於 500 行。
- 修正 service package 層級的 local-core root 解析為 `parents[4]`，避免從 `backend/app/services/object_runtime/` 解析到 workspace 上層。
- 移除 service modules 內殘留的 FastAPI route decorators；endpoint ownership 只留在 `backend/app/routes/core/workspace/object_runtime.py`。
- `route_services._sync_module_aliases()` 現在會把 route/test monkeypatch 的 helper alias 同步到所有持有該名稱的子模組，避免拆檔後測試或 runtime 走回真實 store/registry。
- 驗證結果：object runtime contract suite 30 passed；meeting graph/command backend suite 18 passed；py_compile、diff whitespace、註釋規則掃描通過。

### Product Slice A: Role-bearing Object Outliner

- `ObjectOutlinerPanel` 不再把 Work view 左欄當作 `Focus / Relations / Assets` 的 lane mirror，而是投影為 `Target`、`Sources`、`Evidence`、`Constraints`、`Outputs`、`Review`。
- Outliner 資料來源包括 selected object summary、attach response attachments/target/staged refs/review routes、graph guidance 的 `target_ref` / `proposal_ref`，以及 output/artifact graph nodes。
- 缺少 target 時會以 placeholder row 顯示缺口；已投影 target/proposal/output 時則進入對應 role section，仍只選 graph node 或提示缺口，不新增繞過 Command Ledger 的 action button。
- Layout regression 已覆蓋 target、source、review、output role sections；Meeting Workbench regression 維持 10 files / 43 tests passed。

### Product Slice B: Context Bar role 與 missing-context chips

- `meetingWorkbenchStatus.ts` 新增 `getMeetingFocusRole()` 與 `getMeetingMissingContext()`，由 selected object summary、attach response、graph guidance `target_ref` metadata 判斷焦點物件 role 與是否缺少 target。
- `AOLMeetingBottomShell.tsx` 只負責把 helper 結果轉為 i18n label 並傳入 header；`SemanticFlowCanvas.tsx` 的 `MeetingHeaderToolbar` 只渲染 `Role` 與 `Missing` chip，不承擔 outliner 或 graph 推導邏輯。
- Context Bar 的缺失提示目前只表達缺少 target，不新增散落 action button；實際補齊仍應走 `@` mention、object attach、command template，再進入 `MeetingCommandEnvelope`。
- 已補英文、繁中、日文 i18n key；實作檔與測試檔新增掃描未出現中文註釋、`TODO` 或 `FIXME`。
- 驗證結果：`meetingWorkbenchStatus.spec.ts` + `AOLMeetingBottomShellLayout.spec.tsx` 共 13 tests passed；整組 Meeting Workbench regression 為 10 files / 44 tests passed。

### Product Slice C: Command Dock missing-context guidance

- `MeetingCommandBar` 現在接收同一個 `missingContextLabel`，在輸入框下方顯示缺少角色提示，將 Context Bar 的缺口導回 `@` 引用與 command 輸入。
- 這一刀沒有把 missing-context chip 做成執行按鈕，也沒有直接禁用一般 submit；在 pack guidance required-role 強驗證完成前，Command Dock 只提示缺口，避免誤傷一般 chat 或分析指令。
- Mention picker 改為相對整個輸入區 `bottom-full` 顯示，避免新增缺口提示後和 picker 發生重疊。
- 新增 `CommandDock.spec.tsx`，覆蓋缺少上下文提示、`aria-describedby` 與缺口存在時仍由 Command Dock submit。
- 驗證結果：`CommandDock.spec.tsx` + `AOLMeetingBottomShellLayout.spec.tsx` 共 12 tests passed；整組 Meeting Workbench regression 為 11 files / 46 tests passed。

### Product Slice D: Context Bar chip navigation

- `meetingWorkbenchStatus.ts` 新增 `getMeetingNextStepNodeId()`，將 Context Bar 的 next-step chip 綁回 `Next`、blocked/error 或 guidance graph node，而不是只顯示靜態文字。
- `MeetingHeaderToolbar` 的 Next 與 Missing chip 現在是 graph navigation / input-assist 控制：Next 只選中 graph node，Missing 只選中缺失角色狀態，不觸發 runtime dispatch。
- `ObjectOutlinerPanel` 的 `Missing target` placeholder 可被選中並高亮；`AOLMeetingBottomShell` 在空 command 時以 `@` 打開 mention 入口，仍然導回 Command Dock 與 `MeetingCommandEnvelope`。
- 新增/調整 layout regression 覆蓋 next chip navigation、missing chip callback、missing placeholder selection；未新增任何散落 execution action button。
- 驗證結果：`meetingWorkbenchStatus.spec.ts` + `AOLMeetingBottomShellLayout.spec.tsx` 共 15 tests passed；整組 Meeting Workbench regression 為 11 files / 48 tests passed。

### Product Slice E: Inspector selected-guidance focus

- `MeetingWorkInspectorPanel` 現在會在 Work-view Guidance inspector 頂部顯示被選中的 guidance node，而不是只在下方列表呈現所有 guidance cards。
- Selected guidance focus 會顯示 reason、command template、target ref、proposal ref 與 review routes，讓 Canvas selection、Inspector decision context、Command Dock draft 形成同一條使用者可理解的協作路徑。
- Guidance card 列表中的 target/proposal refs 不再依賴 command template 才顯示；沒有 template 的 guidance 仍可作為關係、提案、審查入口的上下文證據。
- 這一刀沒有新增 Inspector 內的執行按鈕；review route 保持為審查入口，runtime work 仍必須經由 Command Dock 與 `MeetingCommandEnvelope`。
- 新增 `MeetingWorkInspectorPanel.spec.tsx`，直接覆蓋 selected guidance focus 的 reason/template/target/proposal/review route 與 bounded relation 顯示。
- 驗證結果：`MeetingWorkInspectorPanel.spec.tsx` + `AOLMeetingBottomShellLayout.spec.tsx` 共 11 tests passed；整組 Meeting Workbench regression 為 13 files / 49 tests passed。

### Product Slice F: Command Dock chrome i18n

- `CommandDock.tsx` 的 visible copy、placeholder、aria label、tool selector copy、mention picker copy、loading/error/empty copy 轉為 Workbench i18n keys。
- 英文、繁中、日文 locale 同步補齊，讓正式 UI 以 i18n 英文基底擴展，而不是把英文硬寫在 component 裡。
- Command submit button 新增穩定 `meeting-command-submit` test id；既有 dispatch/mention specs 改用 test id 驗證 submit，避免多國語系 aria label 造成測試脆弱。
- 這一刀不改 command routing、不新增 action button、不改 `MeetingCommandEnvelope` 契約；完整 required-role validation 仍是後續產品 gate。
- 驗證結果：`CommandDock.spec.tsx` + dispatch/mentions focused regression 共 12 tests passed；整組 Meeting Workbench regression 為 13 files / 49 tests passed。

### Product Slice G: Guidance required-role command validation

- `ObjectGuidanceCard` generic contract 新增 `required_roles`，並在 `/object-graph/project` normalization 中保留 pack-projected required context roles。
- Frontend object graph guidance node metadata 現在攜帶 `required_roles`；如果 pack 沒有明確給 required roles，但 guidance 投影了 `target_ref`，Command validation 會把它視為需要 `target` context。
- 新增 `meetingCommandValidation.ts`，集中讀取 guidance required roles、比對 command envelope 的 `object_action_entries`，並格式化缺失 role。
- `meetingCommandSubmit.ts` 在建立 local task、開 console、POST `/meetings/{meeting_id}/commands` 前先檢查 selected guidance 的 required roles；缺少必要 role 時只顯示 Command Dock 下方 dispatch error，保留 command draft，不寫 command ledger。
- Work-view Guidance inspector 顯示 required context，讓使用者知道為什麼必須用 `@` 引用補齊，而不是誤以為選中 guidance 等於已經帶入 target。
- 新增 `meetingCommandValidation.spec.ts` 與 dispatch regression：選中 `Director framing` guidance 後若 command draft 沒有 target mention，submit 會被擋下，且不會 POST `/commands`、不會打開 console。
- 這一刀仍不新增散落 action button，也不讓 frontend 接管 route-owned dispatch；只把缺口導回 `@` reference 與 `MeetingCommandEnvelope`。
- 驗證結果：focused validation/dispatch/inspector 共 11 tests passed；整組 Meeting Workbench regression 為 14 files / 53 tests passed；backend py_compile passed，object graph registry projection test 1 passed。

### Product Slice H: AOL session notification closure

- 新增 `meetingSessionNotifications.ts`，定義本地 `meeting-session-notification` event contract，包含 workspace、meeting、tone、title、message 與 command id。
- 新增 `MeetingSessionNotification.tsx`，在 Meeting Workbench 內以 aria-live strip 呈現 command accepted、completed、failed、awaiting runtime 等 session notification。
- `AOLMeetingBottomShell` 透過 `useMeetingSessionNotification.ts` 只接收當前 workspace/meeting 的 notification event；切換 meeting 時清空目前通知，避免跨 session 汙染，並避免 shell wrapper 回到 500 行以上。
- `meetingCommandSubmit.ts` 在 command ledger accepted、object-action completed/failed、object-action-plan rejected/warning、playbook accepted、chat accepted、dispatch error 等狀態發出 session notification。
- Notification 是 command-ledger/runtime state 的投影，不是新的 dispatch 入口；不新增 action button，也不新增 dedicated backend stream。
- 新增 `meetingSessionNotifications.spec.ts` 與 dispatch regression，覆蓋 notification event 解析、command accepted info notification、route contract error notification。
- 驗證結果：focused notification/dispatch 共 9 tests passed；整組 Meeting Workbench regression 為 15 files / 55 tests passed。

### Product Slice I: IG/PD product fixture gate

- `useMeetingObjectContextData.ts` 改為 pack workbench 傳入的 `summary`、`selection`、`attachResponse` 優先於 active meeting session metadata，避免 PD storyboard 從 pack workbench 打開 shell 時被目前 meeting session 的 IG source metadata 覆蓋。
- `meetingWorkbenchTestData.ts` 新增 Performance Direction storyboard summary 與 attach response fixture，用同一個 Meeting Workbench shell 驗證 PD 來源物件。
- `meetingWorkbenchGraphFixtureResponses.ts` 的 `/object-graph/project` mock 依請求 object refs 回傳 IG reference projection 或 PD storyboard projection，而不是永遠回傳中性 `fixture_pack` projection。
- IG projection 以 `directs` relation 指向 PD storyboard，並投影 `Director framing` guidance、PD proposal ref、PD review route、`target` required role，驗證 IG reference 可透過 bounded graph guidance 導向 PD 下一步。
- PD projection 以 `guided_by` relation 指回 IG source，並投影 `Reels generation pass` guidance 與 generated reels target ref，驗證 PD storyboard workbench 能走同一 shell 與 pack tool selection。
- 新增 `AOLMeetingBottomShellPackFixtures.spec.tsx`：第一個 case 驗證 IG guidance 缺少 `@storyboard` target 時不寫 Command Ledger，補入 PD registry mention 後才寫 `/meetings/{meeting_id}/commands`，且 command payload 含 `source=ig/reference/ref_global` 與 `target=performance_direction/storyboard/pd_session_1`；第二個 case 驗證 PD storyboard prop context 不被 session metadata 覆蓋，並會選中 `generate_reels_asset` pack tool。
- 測試明確斷言沒有呼叫 `/api/v1/capabilities/performance_direction/sessions` 或 `/object-actions/invoke`，避免 local-core shell 用 pack-specific API 或 frontend direct dispatch 繞過 Command Ledger。
- 驗證結果：layout/dispatch/pack-fixture focused regression 為 3 files / 19 tests passed；整組 Meeting Workbench regression 為 16 files / 57 tests passed；backend py_compile passed，object graph registry projection test 1 passed；註釋/中文/TODO 掃描無命中；`git diff --check` 通過並僅保留既有 PowerShell CRLF 警告。

## 4. Verification SOP

1. Meeting Workbench compatibility and focused helpers:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && ./node_modules/.bin/vitest run src/components/capabilities/meeting-workbench/*.spec.ts src/components/capabilities/meeting-workbench/*.spec.tsx --config vitest.config.ts --testTimeout=15000`
   - Last result: 16 test files passed, 57 tests passed.

2. AOL Runtime Shell / legacy host compatibility:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && ./node_modules/.bin/vitest run src/components/capabilities/aol-runtime-shell/*.spec.tsx src/components/capabilities/AddressableObjectHostShell.spec.tsx --config vitest.config.ts --testTimeout=15000`
   - Last result: 4 test files passed, 9 tests passed.

3. Backend command-envelope contract seed:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && python -m pytest backend/tests/test_meeting_command_parser.py backend/tests/test_meeting_command_envelope.py backend/tests/test_meeting_execution_graph_commands.py backend/tests/test_meeting_command_status_sync.py`
   - Last result: 4 test files passed, 15 tests passed.

4. Backend syntax gate:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m py_compile backend/app/services/object_runtime/*.py backend/app/routes/core/workspace/object_runtime.py backend/app/routes/core/workspace/meeting_graph.py backend/app/models/meeting_graph.py backend/app/models/object_runtime/__init__.py backend/app/models/object_runtime/actions.py backend/app/models/object_runtime/catalog.py backend/app/models/object_runtime/graph.py backend/app/models/object_runtime/instance_index.py backend/app/models/object_runtime/materialization.py backend/app/models/object_runtime/meeting.py backend/app/models/object_runtime/refs.py backend/app/models/object_runtime/selection.py backend/app/services/meeting_graph/projection_builder.py backend/app/services/meeting_graph/projection_utils.py backend/app/services/meeting_graph/task_projection.py backend/app/services/meeting_graph/event_projection.py`
   - Last result: passed.

5. Object runtime projection syntax gate:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/object_action_planning_runtime_test.py backend/tests/object_instance_registry_runtime_test.py backend/tests/test_object_meeting_attachment.py backend/tests/test_aol_target_only_attach.py backend/tests/routes/core/test_workspace_object_runtime_api.py -q`
   - Last result: 30 tests passed.

6. Diff whitespace gate:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && git diff --check`
   - Last result: passed with existing PowerShell CRLF warnings for `install.ps1`, `scripts/setup.ps1`, `scripts/start.ps1`, and `scripts/start_cli_bridge.ps1`.

7. Large-file line gate:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && wc -l web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx web-console/src/components/capabilities/meeting-workbench/useMeetingMentionItems.ts web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx web-console/src/components/capabilities/meeting-workbench/MeetingDefaultInspectorContent.tsx web-console/src/components/capabilities/meeting-workbench/useMeetingThreadData.ts web-console/src/components/capabilities/meeting-workbench/meetingCommandEvents.ts web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx`
   - Last focused result after Product Slice I: `AOLMeetingBottomShell.tsx` 472 lines, `SemanticFlowCanvas.tsx` 397 lines, `ObjectOutlinerPanel.tsx` 316 lines, `MeetingWorkbenchStage.tsx` 89 lines, `meetingWorkbenchStatus.ts` 117 lines, `MeetingWorkInspectorPanel.tsx` 302 lines, `MeetingWorkInspectorPanel.spec.tsx` 125 lines, `CommandDock.tsx` 212 lines, `CommandDock.spec.tsx` 92 lines, `meetingCommandSubmit.ts` 326 lines, `meetingCommandValidation.ts` 68 lines, `meetingCommandValidation.spec.ts` 67 lines, `MeetingSessionNotification.tsx` 53 lines, `meetingSessionNotifications.ts` 38 lines, `meetingSessionNotifications.spec.ts` 35 lines, `useMeetingSessionNotification.ts` 41 lines, `AOLMeetingBottomShellLayout.spec.tsx` 391 lines, `AOLMeetingBottomShellDispatch.spec.tsx` 310 lines, `AOLMeetingBottomShellPackFixtures.spec.tsx` 151 lines, `meetingWorkbenchGraphFixtureResponses.ts` 205 lines, `meetingWorkbenchTestData.ts` 246 lines, `meetingWorkbenchTestHarness.ts` 376 lines, `backend/app/services/object_runtime/graph_service.py` 449 lines.

8. Runtime shell line gate:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && wc -l web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProviderImpl.tsx web-console/src/components/capabilities/aol-runtime-shell/useAOLRuntimeShellHostController.ts web-console/src/components/capabilities/aol-runtime-shell/useAOLRuntimeSurfaceRegistry.ts web-console/src/components/capabilities/aol-runtime-shell/useRuntimeShellMeetingPaneSizing.ts web-console/src/components/capabilities/aol-runtime-shell/RuntimeObjectPanel.tsx web-console/src/components/capabilities/aol-runtime-shell/RuntimeObjectPreview.tsx web-console/src/components/capabilities/aol-runtime-shell/AddressableObjectPanel.tsx web-console/src/components/capabilities/aol-runtime-shell/AddressableObjectPreview.tsx`
   - Last result: `AOLRuntimeShellProviderImpl.tsx` 92 lines, `useAOLRuntimeShellHostController.ts` 393 lines, `useAOLRuntimeSurfaceRegistry.ts` 74 lines, `useRuntimeShellMeetingPaneSizing.ts` 78 lines, `RuntimeObjectPanel.tsx` 324 lines, `RuntimeObjectPreview.tsx` 293 lines, `AddressableObjectPanel.tsx` 4 lines, `AddressableObjectPreview.tsx` 4 lines.

9. Internal docs location:
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && find docs -maxdepth 4 \\( -name '*2026-05-02*.md' -o -name 'aol-runtime-shell-refactor-plans-2026-05-02' \\) -print`
   - Expected: no first-stage implementation-plan files under public docs.

10. Meeting Graph semantics:
    - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/meeting_execution_graph_object_semantics_test.py backend/tests/test_meeting_execution_graph_commands.py -q`
    - Last result: 6 tests passed.

11. Object Runtime service line gate:
    - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && wc -l backend/app/services/object_runtime/*.py backend/app/routes/core/workspace/object_runtime.py backend/app/routes/core/workspace/meeting_graph.py 'web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx'`
    - Last result: `route_services.py` 142 lines, `object_runtime.py` route 366 lines, `meeting_graph.py` route 137 lines, `meetings/page.tsx` 132 lines; largest object runtime service module is `materialization_service.py` at 459 lines.

12. Backend command and graph combined regression:
    - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/meeting_execution_graph_object_semantics_test.py backend/tests/test_meeting_execution_graph_commands.py backend/tests/test_meeting_command_parser.py backend/tests/test_meeting_command_envelope.py backend/tests/test_meeting_command_status_sync.py -q`
    - Last result: 18 tests passed.

13. Comment and internalization hygiene:
    - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "TODO|FIXME|[\p{Han}]" backend/app/services/object_runtime backend/app/routes/core/workspace/object_runtime.py backend/app/models/object_runtime backend/app/routes/core/workspace/meeting_graph.py backend/app/services/meeting_graph 'web-console/src/app/workspaces/[workspaceId]/meetings'`
    - Last Product Slice I focused result: no matches for `TODO`、`FIXME` 或中文硬編碼 in object-runtime graph contract files, `addressable-object-layer.ts`, and `web-console/src/components/capabilities/meeting-workbench`.

14. Full frontend type-check:
    - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && ./node_modules/.bin/tsc --noEmit --pretty false --project tsconfig.json`
    - Last Product Slice I result: failed on existing repo-wide errors under stale `.next` generated routes and unrelated capability packs/settings/workspace components. After this slice's type fixes, no remaining type-check error references `web-console/src/components/capabilities/meeting-workbench`, `web-console/src/components/capabilities/aol-runtime-shell`, `PerformanceDirectionWorkbenchHost`, or `ReferenceGridCard`.

## 5. Remaining milestones

1. 第一階段 P0 重構可進入收尾驗收；後續不得再把單一拆檔稱為里程碑，除非關閉新的計劃級 gate。
2. 第二階段本輪 product slice 可進入收尾查驗；目前已用 IG/PD product fixtures 證明同一 AOL Runtime Workbench shell 可從 IG reference 與 PD storyboard 進入 guidance、required context、Command Ledger 與 session notification。
3. 後續真正 pack-side backend 接入時，IG/PD pack 仍必須透過 bounded object graph projection、registry refs、command templates、review routes 與 installed-pack runtime contract 供給資料；local-core 不得新增 IG/PD 專屬 business branch。
4. Revisit backend dedicated command-ledger SSE only if the local browser event plus shared workspace SSE fails product latency or scale requirements.

## 6. Risks / open questions

- `AOLMeetingBottomShell.tsx`、`PropertiesInspector.tsx`、object runtime graph service 與新增 pack fixture specs 均低於 500 行；後續主要風險不再是本輪 shell 大檔，而是真實 IG/PD pack backends 接入時是否仍遵守 bounded projection 與 Command Ledger contract。
- `AddressableObjectHostShell.tsx` and `AddressableObjectHostShell.spec.tsx` are now compatibility-only, but app callers still include some legacy import surfaces until their surrounding files are fully renamed.
- `backend/app/services/object_runtime/route_services.py` is now a thin compatibility facade under 500 lines; remaining risk is not line count, but whether future service-level tests should replace route-level monkeypatch compatibility over time.
- Current tests now include the first product Work-view assertions, stage ownership assertions, selected-subgraph Work canvas assertions, task-oriented inspector content assertions, selected-guidance Inspector focus assertions, guidance command-template assertions, guidance review-route assertions, guidance required-role command validation assertions, AOL session notification assertions, dense provenance overflow grouping assertions, and command-ledger local refresh event assertions.
- The meeting central collaboration platform now has backend command rows, frontend command submit writes them first, object-action/selected playbook/ordinary chat commands are route-owned, task/chat completion can update command status, command graph nodes remain visible after lifecycle mapping, the active Meeting Workbench refreshes from workspace SSE events, and the default Work view no longer leads with raw node/trace counts. It is still not complete until the full four-editor UX is implemented.
- Full repo type-check was not used as the completion gate for this milestone because the repo has unrelated pre-existing type-check failures outside this refactor scope.
