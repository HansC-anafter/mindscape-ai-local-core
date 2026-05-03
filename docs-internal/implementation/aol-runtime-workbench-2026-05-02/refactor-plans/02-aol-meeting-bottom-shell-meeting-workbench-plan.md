# AOLMeetingBottomShell To Meeting Workbench Refactor Plan

Target file: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`

## 1. Problem list

1. **The file is a 4181-line monolith**: it contains domain types, graph projection, API helpers, fetch effects, mention parsing, object action planning/invocation, canvas rendering, inspector rendering, command bar, and shell orchestration. Evidence: E1, E2, E3, E4, E5, E6. Severity: 5. Detection: 4. Priority: 20.
2. **The primary UI model is still fixed graph lanes**: `GRAPH_LANES` and `MeetingTaskCanvas` render `Context`, `Object Graph`, `Commands`, `Runs`, `Outputs`, `Artifacts`, and `Next` as the main canvas. Evidence: E1, E3. Severity: 5. Detection: 3. Priority: 15.
3. **The command submit path is not isolated behind a command envelope boundary**: `handleSubmitCommand` builds local task nodes, resolves mentions, requests object action plans, invokes object actions, or calls `sendMessage` in the same component. Evidence: E5. Severity: 5. Detection: 5. Priority: 25.
4. **Debug/proof views and product views are mixed**: inspector tabs include `Trace`, `Graph`, `Prompts`, and `Patch`, and trace view renders raw events and JSON inside the default component tree. Evidence: E1, E4. Severity: 4. Detection: 3. Priority: 12.

## 2. Evidence

E1. The file declares Meeting Workbench types, inspector tabs, graph lanes, zoom constants, mention regex, and component props in one top-level block. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L32-L254`.

E2. `projectMeetingGraph` merges events, artifacts, local tasks, object graph nodes, execution graph nodes, execution graph edges, loading states, and view mode into one projection. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1073-L1230`.

E3. `MeetingHeaderToolbar` and `MeetingTaskCanvas` render graph view mode controls, node/trace counts, pan/zoom behavior, and fixed lanes. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1872-L2248`.

E4. `MeetingInspectorPanel` renders object, runtime, session, trace, graph, prompts, and patch views, including raw replay events and JSON. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2475-L2906`.

E5. `AOLMeetingBottomShell` owns data fetching, session selection, object graph fetch, object index sync, playbook fetch, mention completion, runtime state, projection composition, and command submit dispatch. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2956-L4181`.

E6. The refactor inventory counted the file at 4181 lines and marked it as the first priority monolithic meeting bottom shell. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L68-L79`.

## 3. Proposed changes

### Change 1: Extract stable type and API modules

Resolves Problems 1 and 3.

- Add `meetingWorkbenchTypes.ts` for `MeetingNode`, `MeetingGraphEdge`, `MeetingSessionSummary`, `MeetingEventSummary`, `MeetingArtifactSummary`, `MeetingPackTool`, `MeetingMention*`, and props.
- Add `meetingApi.ts` for `fetchApiJson`, `postApiJson`, meeting sessions/events/artifacts/execution graph fetchers, pack tool fetch, mention completion, and object index sync.
- Keep API paths unchanged.

### Change 2: Extract projection and command impact logic

Resolves Problems 1 and 2.

- Add `meetingGraphProjection.ts` for coercers, graph lanes as debug config, `projectMeetingGraph`, event/artifact builders, and object graph node builders.
- Add `meetingCommandImpact.ts` for `buildCommandImpact`, command impact node/edge collection, and trace fallback impact.
- Keep current output shape initially so wrapper tests remain valid.

### Change 3: Extract mention and object action boundaries

Resolves Problems 1 and 3.

- Add `meetingMentions.ts` for mention regex, token parsing, registry mention item conversion, mention extraction, and role mapping.
- Add `meetingObjectActions.ts` for `buildObjectActionPlanEntries`, `requestObjectActionPlan`, `invokeObjectAction`, and `isPlannedObjectActionPlan`.
- Keep `handleSubmitCommand` in the wrapper only until backend `MeetingCommandEnvelope` / Command Ledger lands.

### Change 4: Extract UI regions into Meeting Workbench components

Resolves Problems 1, 2, and 4.

- Add:
  - `MeetingWorkbenchView.tsx`
  - `MeetingContextBar.tsx`
  - `ObjectOutliner.tsx`
  - `SemanticFlowCanvas.tsx`
  - `PropertiesInspector.tsx`
  - `CommandDock.tsx`
  - `TraceDebugView.tsx`
- Keep `AOLMeetingBottomShell.tsx` as a compatibility wrapper that loads data and passes props to `MeetingWorkbenchView`.
- Do not implement the second-stage visual UX yet; preserve current behavior while moving code.

### Change 5: Rename view semantics without breaking debug substrate

Resolves Problems 2 and 4.

- Architecture/code: `MeetingWorkbenchView`.
- Product copy: `Meeting Workbench`.
- Debug/provenance copy: `Meeting Graph` only inside `TraceDebugView` or debug labels.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx --environment jsdom`
   Expected: compatibility wrapper preserves current behavior.
   Fail: graph lanes, command submit, object graph, session switch, or mention tests regress.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg --files web-console/src/components/capabilities/meeting-workbench | rg "meetingWorkbenchTypes|meetingGraphProjection|meetingCommandImpact|meetingMentions|meetingObjectActions|meetingApi|MeetingWorkbenchView|CommandDock|TraceDebugView"`
   Expected: extracted modules exist.
   Fail: all logic remains in `AOLMeetingBottomShell.tsx`.

3. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && wc -l web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`
   Expected: wrapper line count is materially reduced after extraction.
   Fail: file remains near 4181 lines after the refactor.

## 5. Automated test plan

- Add `meetingGraphProjection.test.ts`.
  Scenario: events, artifacts, execution graph nodes, and object graph nodes produce the same current projection.
  Assertions: command lane, artifact lane, trace counts, and ready node remain stable.
  Prevents: Problems 1 and 2.

- Add `meetingMentions.test.ts`.
  Scenario: registry refs, raw host-native mentions, storyboard/scene/character refs.
  Assertions: pack-owned unresolved raw tokens are not synthesized into object refs.
  Prevents: Problem 3.

- Add `meetingObjectActions.test.ts`.
  Scenario: object action plan/invoke payloads from selected object and mentions.
  Assertions: `meeting_id`, entries, selected object URI, and request context match current behavior.
  Prevents: Problem 3.

- Add `MeetingWorkbenchView.spec.tsx`.
  Scenario: render with mocked projection and callbacks.
  Assertions: view renders current toolbar/canvas/inspector/dock through extracted regions.
  Prevents: Problems 1, 2, and 4.

## 6. Risks / open questions

- Do not rewrite UX while extracting. Behavior-preserving refactor first, UX iteration second.
- `handleSubmitCommand` should not be fully redesigned until backend command ledger endpoints exist.
- The current fixed lane board may remain as a debug view temporarily; removing it during this phase would hide proof coverage.
