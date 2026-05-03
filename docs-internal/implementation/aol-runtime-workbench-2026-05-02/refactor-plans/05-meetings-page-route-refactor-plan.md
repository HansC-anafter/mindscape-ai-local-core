# Meetings Page Route Refactor Plan

Target file: `web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx`

## 1. Problem list

1. **The route is named `MeetingWorkbenchPage` but renders a historical records surface**: visible copy says `Meeting Records`, `Session history, decisions, and action items`, which can be confused with the new `Meeting Workbench` view. Evidence: E1, E3. Severity: 3. Detection: 4. Priority: 12.
2. **The route mixes page state, API fetch, list/detail components, scene patch console, governed memory, and workflow evidence in one 760-line file**. Evidence: E1, E2, E3. Severity: 4. Detection: 3. Priority: 12.
3. **The route can be mistaken for the AOL Runtime Shell root**: it fetches `meeting-sessions` and opens session details, but it is a standalone records/admin page, not the bottom/overlay shell opened by pack workbenches. Evidence: E3, E4. Severity: 4. Detection: 4. Priority: 16.

## 2. Evidence

E1. The file declares page-local types such as `MeetingSession`, `CanonicalMemoryLink`, `WorkflowEvidenceDiagnostics`, and `ActionItem`, plus helper functions, at the top of the route file. Source: `web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx:L1-L140`.

E2. The route imports governed memory, impact graph, workflow evidence, and scene patch console components directly. Source: `web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx:L7-L17`.

E3. `MeetingWorkbenchPage` fetches `meeting-sessions`, maintains selected session state, updates query params, and renders `Meeting Records` with session list/detail layout. Source: `web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx:L589-L760`.

E4. The refactor inventory counted the file at 760 lines and classified it as a legacy standalone meeting workbench/admin surface that should not become the new shell architecture root. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L68-L79`.

## 3. Proposed changes

### Change 1: Rename route-level intent in code and copy

Resolves Problems 1 and 3.

- Rename internal component to `MeetingRecordsPage`.
- Keep route path `/workspaces/[workspaceId]/meetings` unchanged.
- Use product copy `Meeting Records` or `Meeting History`, not `Meeting Workbench`.
- Do not mount `AOLRuntimeShell` from this page as part of this refactor.

### Change 2: Extract page types and API hooks

Resolves Problem 2.

- Add `web-console/src/app/workspaces/[workspaceId]/meetings/meetingRecords.types.ts`.
- Add `meetingRecordsApi.ts` for fetching meeting sessions and full session detail.
- Keep query parameter behavior unchanged: `project_id`, `session_id`, `open_patch`.

### Change 3: Extract route components

Resolves Problem 2.

- Add:
  - `MeetingRecordsHeader.tsx`
  - `MeetingSessionList.tsx`
  - `MeetingSessionCard.tsx`
  - `MeetingSessionDetailPanel.tsx`
- Keep current `SessionDetail` behavior intact during extraction.

### Change 4: Document boundary with AOL Runtime Shell

Resolves Problem 3.

- Add a comment or docstring near the default export: this route is historical session records, not the AOL Runtime Workbench runtime shell.
- Link to the shell refactor inventory in implementation notes if needed.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "MeetingWorkbenchPage|MeetingRecordsPage|Meeting Records|Meeting Workbench" 'web-console/src/app/workspaces/[workspaceId]/meetings'`
   Expected: default export uses `MeetingRecordsPage`; route copy stays `Meeting Records`; no product shell naming collision.
   Fail: route still presents itself as the new Meeting Workbench.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/app/workspaces/[workspaceId]/meetings --environment jsdom`
   Expected: route/component tests pass if present.
   Fail: query selection or detail panel behavior changes.

3. Manual route check: open `/workspaces/{workspaceId}/meetings?session_id={id}`.
   Expected: selected session loads and detail panel opens.
   Fail: session query stops selecting the record.

## 5. Automated test plan

- Add `meetingRecordsApi.test.ts`.
  Scenario: builds list/detail fetch URLs with project and session params.
  Assertions: endpoints match current `meeting-sessions` paths.
  Prevents: Problem 2.

- Add `MeetingRecordsPage.spec.tsx`.
  Scenario: loading, error, empty, session selection, query update, detail close.
  Assertions: visible title is `Meeting Records`; route does not render `AOLRuntimeShell`.
  Prevents: Problems 1 and 3.

## 6. Risks / open questions

- This route may have users who expect the current path; do not rename route path.
- Scene patch and governed memory detail components may carry their own test requirements; extract without changing their behavior.
- If product navigation later wants `Runtime Workbench`, create a separate shell entry rather than overloading `/meetings`.
