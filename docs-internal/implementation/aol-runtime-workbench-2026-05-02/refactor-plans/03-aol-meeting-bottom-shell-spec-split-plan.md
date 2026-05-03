# AOLMeetingBottomShell Spec Split Refactor Plan

Target file: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx`

## 1. Problem list

1. **One 1251-line spec file covers unrelated modules that should be split**: shell rendering, execution graph projection, object graph projection, sessions, events, inspector, zoom/pan, mentions, object action dispatch, session switch, and pack dispatch are all tested through `AOLMeetingBottomShell`. Evidence: E1, E2. Severity: 4. Detection: 4. Priority: 16.
2. **The spec locks tests to the monolithic component import**: all scenarios render `AOLMeetingBottomShell`, which will slow extraction unless lower-level modules get direct tests first. Evidence: E1, E3. Severity: 4. Detection: 4. Priority: 16.
3. **Several assertions encode legacy graph-first copy and test ids**: current assertions expect `meeting-graph-lane-*`, `Object Graph`, and graph-first behavior; these need to move to debug/projection tests before the product UX phase. Evidence: E3. Severity: 3. Detection: 4. Priority: 12.

## 2. Evidence

E1. The file imports `AOLMeetingBottomShell` and defines one `describe('AOLMeetingBottomShell')` suite. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx:L5-L31`.

E2. The test setup mocks endpoints for object completion, object action plan/invoke, object graph projection, meeting sessions, meeting events, execution graph, and artifacts in one file. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx:L62-L589`.

E3. Test cases cover graph-first shell, execution graph nodes, bounded object graph, session filtering, persisted events, inspector, zoom, pan, mention picker, registry objects, object action dispatch, session switch, command task node, and selected pack tool dispatch. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx:L623-L1209`.

E4. The refactor inventory counted the spec at 1251 lines and marked it as regression coverage for the monolithic bottom shell. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L68-L79`.

## 3. Proposed changes

### Change 1: Keep this file as compatibility wrapper coverage

Resolves Problems 1 and 2.

- Rename the test title only after `AOLMeetingBottomShell.tsx` becomes a wrapper.
- Keep a small smoke suite here:
  - wrapper renders
  - existing props still accepted
  - active meeting loads
  - command dock can submit through old wrapper path

### Change 2: Move projection tests to pure module specs

Resolves Problems 1 and 3.

- Move execution graph/event/artifact/object graph projection assertions into `meetingGraphProjection.test.ts`.
- Move command impact assertions into `meetingCommandImpact.test.ts`.
- Keep legacy `meeting-graph-lane-*` assertions only in projection/debug tests.

### Change 3: Move command and mention tests to focused specs

Resolves Problems 1 and 2.

- Move mention parsing and registry completion cases into `meetingMentions.test.ts`.
- Move object action plan/invoke payload tests into `meetingObjectActions.test.ts`.
- Move command bar interaction into `CommandDock.spec.tsx`.

### Change 4: Move UI region tests to extracted components

Resolves Problems 1 and 2.

- Add specs for `MeetingWorkbenchView`, `SemanticFlowCanvas`, `PropertiesInspector`, and `TraceDebugView`.
- Do not duplicate every wrapper test; assert component-level behavior where the logic now lives.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx --environment jsdom`
   Expected: compatibility smoke tests pass.
   Fail: wrapper behavior breaks.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench --environment jsdom`
   Expected: split module tests and wrapper tests pass together.
   Fail: behavior only passes through wrapper but module tests fail.

3. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "describe\\('AOLMeetingBottomShell'|meetingGraphProjection|meetingMentions|meetingObjectActions|CommandDock" web-console/src/components/capabilities/meeting-workbench`
   Expected: old describe suite is small and new focused suites exist.
   Fail: all major scenarios remain in the monolithic spec.

## 5. Automated test plan

- `meetingGraphProjection.test.ts`: projection from events, artifacts, local tasks, object graph, and execution graph.
- `meetingCommandImpact.test.ts`: selected command impact nodes/edges/events/outputs/artifacts.
- `meetingMentions.test.ts`: raw mention fallback and registry-backed object refs.
- `meetingObjectActions.test.ts`: action plan entries, plan request payload, invoke request payload.
- `SemanticFlowCanvas.spec.tsx`: lane/debug canvas behavior while second-stage UX is pending.
- `CommandDock.spec.tsx`: command input, mention insert, submit gating.

## 6. Risks / open questions

- Splitting tests before extracting production modules may duplicate fixtures. Extract shared fixtures first.
- Some old test ids contain `meeting-graph`; keep them for debug compatibility until UX pass.
- Do not delete wrapper coverage; it protects current capability pages while imports migrate.
