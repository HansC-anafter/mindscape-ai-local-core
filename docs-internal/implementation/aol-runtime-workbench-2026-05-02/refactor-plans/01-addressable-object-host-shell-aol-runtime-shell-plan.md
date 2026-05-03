# AddressableObjectHostShell To AOL Runtime Shell Refactor Plan

Target file: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx`

## 1. Problem list

1. **Architecture name and product name are collapsed into legacy Addressable Object naming**: the file owns the shared shell/provider/bridge but exports `AddressableObjectHostShell` and `AddressableObjectHostProvider`, so new AOL Runtime Shell work would inherit old names. Evidence: E1, E6. Severity: 4. Detection: 3. Priority: 12.
2. **One file owns too many shell responsibilities**: provider state, surface registration, object selection, preview rendering, role selection, meeting pane, rail anchors, bridge slot, and exported hooks are implemented in one 1621-line file. Evidence: E1, E2, E3, E4, E5. Severity: 5. Detection: 4. Priority: 20.
3. **Visible copy still frames the runtime workbench as a graph shell**: the meeting pane renders `Meeting Graph`, graph shell labels, and graph-focused ARIA labels even though the architecture rename requires `AOL Runtime Shell` for code and `AOL Runtime Workbench` / `Meeting Workbench` for product/view copy. Evidence: E2, E3. Severity: 4. Detection: 3. Priority: 12.
4. **Compatibility callers still import the legacy shell directly**: workspace layout and capability pages import from this file, so a hard rename would break current callers unless aliases are preserved. Evidence: E7. Severity: 4. Detection: 4. Priority: 16.

## 2. Evidence

E1. `AddressableObjectHostShell.tsx` defines shell state, provider props, controller interface, idle state, and `AddressableObjectHostContext` in the same file. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx:L29-L92`.

E2. `AddressableObjectMeetingPane` renders the visible pane title `Meeting Graph`, ARIA label `AOL meeting graph`, pane size controls, and mounts `AOLMeetingBottomShell`. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx:L526-L620`.

E3. `AddressableGraphShellAnchor` and `AddressableObjectToolRail` expose `Open graph shell`, `No active workbench surface for graph shell`, and `Graph` copy in the global rail. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx:L970-L1052`.

E4. `AddressableObjectHostProviderInner` begins at line 1059 and owns registered surfaces, panel state, meeting pane height, and request epoch refs. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx:L1059-L1525`.

E5. The exported provider, bridge slot, shell, and hook are all at the bottom of the same file. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx:L1526-L1621`.

E6. The refactor inventory counted the file at 1621 lines and identified it as the current AOL host/provider/panel/anchor implementation despite old `AddressableObject` naming. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L68-L79`.

E7. Current call sites import `AddressableObjectHostProvider` / `AddressableObjectHostShell` from this file in workspace layout and capability pages. Source: `web-console/src/app/workspaces/[workspaceId]/layout.tsx:L6-L42`, `web-console/src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.tsx:L8-L435`, `web-console/src/app/workspaces/[workspaceId]/capabilities/performance_direction/PerformanceDirectionWorkbenchHost.tsx:L7-L54`.

## 3. Proposed changes

### Change 1: Create the AOL Runtime Shell module boundary

Resolves Problems 1 and 2.

- Add `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellContext.ts`.
- Move `AddressableObjectSurfaceContext`, `RegisteredSurfaceContext`, `AOLPanelState`, provider props, controller interface, idle state, and context into this module.
- Rename types at the architecture boundary:
  - `AddressableObjectSurfaceContext` -> `AOLRuntimeSurfaceContext`
  - `AOLPanelState` -> `AOLRuntimeShellState`
  - `AddressableObjectHostController` -> `AOLRuntimeShellController`

### Change 2: Extract provider/state into `AOLRuntimeShellProvider.tsx`

Resolves Problems 1, 2, and 4.

- Move `AddressableObjectHostProviderInner`, state reducers/callbacks, resize state, and surface registration into `AOLRuntimeShellProvider.tsx`.
- Export `AOLRuntimeShellProvider` and `useAOLRuntimeShellController`.
- Keep compatibility aliases from the old file:
  - `AddressableObjectHostProvider = AOLRuntimeShellProvider`
  - `useAddressableObjectHostController = useAOLRuntimeShellController`

### Change 3: Extract UI shell regions

Resolves Problems 2 and 3.

- Move preview UI into `ObjectPreviewPanel.tsx`.
- Move selection/candidate/role panel into `ObjectSelectionPanel.tsx`.
- Move rail/anchors into `RuntimeShellAnchorRail.tsx`.
- Move meeting pane into `RuntimeShellPanel.tsx`.
- Product copy rules:
  - code/component name: `AOLRuntimeShell`
  - product surface copy: `AOL Runtime Workbench` / `Runtime Workbench`
  - active session view copy: `Meeting Workbench`
  - debug copy only: `Meeting Graph`

### Change 4: Keep the old file as a compatibility facade

Resolves Problem 4.

- Keep `AddressableObjectHostShell.tsx` as a thin re-export and wrapper during this refactor.
- Export `AOLRuntimeShell` from the new directory.
- Make `AddressableObjectHostShell` call `AOLRuntimeShell` without changing caller behavior.
- Do not update every caller in the same patch unless the compatibility wrapper is already passing tests.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/AddressableObjectHostShell.spec.tsx --environment jsdom`
   Expected: existing host shell behavior still passes through compatibility exports.
   Fail: any missing `aol-global-anchor`, `aol-host-panel`, `aol-meeting-pane`, or `aol-meeting-bottom-shell` assertion.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "AddressableObjectHostShell|AddressableObjectHostProvider|AOLRuntimeShell|AOLRuntimeShellProvider" web-console/src`
   Expected: new modules exist, old imports are either compatibility imports or intentionally migrated imports.
   Fail: new code imports old names directly outside compatibility callers.

3. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "Meeting Graph|graph shell" web-console/src/components/capabilities/aol-runtime-shell web-console/src/components/capabilities/AddressableObjectHostShell.tsx`
   Expected: `Meeting Graph` only appears in explicit debug/trace labels, not primary shell title.
   Fail: primary product title remains `Meeting Graph`.

## 5. Automated test plan

- Add `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProvider.spec.tsx`.
  Scenario: multiple registered capability surfaces share one provider, one rail, and one panel.
  Assertions: one global anchor, one shell rail, one meeting pane after opening.
  Prevents: Problems 1, 2, and 4.

- Add `web-console/src/components/capabilities/aol-runtime-shell/RuntimeShellPanel.spec.tsx`.
  Scenario: open meeting pane with object context and without object context.
  Assertions: product/view title copy uses `Meeting Workbench`; compatibility `AOLMeetingBottomShell` still mounts.
  Prevents: Problem 3.

- Keep `AddressableObjectHostShell.spec.tsx` as a compatibility suite until all callers migrate.

## 6. Risks / open questions

- Converting all callers to `AOLRuntimeShell` in one patch is avoidable risk; use compatibility aliases first.
- Some tests assert old `graph shell` semantics; update only after the UI copy rule is explicit.
- The provider currently owns both selection and meeting-pane state. Splitting state too early could create stale surface registration bugs.
