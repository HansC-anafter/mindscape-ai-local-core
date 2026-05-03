# AddressableObjectHostShell Spec Split Refactor Plan

Target file: `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx`

## 1. Problem list

1. **The 761-line spec covers provider, bridge, object panel, candidate picker, role control, graph shell anchor, meeting pane, and compatibility behavior in one file**. Evidence: E1, E2. Severity: 4. Detection: 4. Priority: 16.
2. **The spec imports only legacy names**: it imports `AddressableObjectHostProvider` and `AddressableObjectHostShell`, so it does not verify the new `AOLRuntimeShell` exports that the rename requires. Evidence: E1. Severity: 4. Detection: 4. Priority: 16.
3. **The spec asserts graph shell semantics that should become workbench/view semantics**: tests expect `aol-graph-shell-anchor`, `aol-meeting-pane`, and `aol-meeting-bottom-shell`, while product copy should move to AOL Runtime Workbench / Meeting Workbench. Evidence: E2. Severity: 3. Detection: 4. Priority: 12.

## 2. Evidence

E1. The spec imports `AddressableObjectHostProvider` and `AddressableObjectHostShell` from `./AddressableObjectHostShell` and declares one `AddressableObjectHostProvider` suite. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx:L6-L19`.

E2. Test cases cover shared anchors, opening graph shell from existing sessions, replacing selected object, shared expansion surface, selected generic context role, and ambiguous selection disambiguation. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx:L134-L750`.

E3. The tests assert one global anchor, one host panel, graph shell anchor availability, meeting pane, meeting bottom shell, and no legacy meeting chat. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx:L190-L218`, `web-console/src/components/capabilities/AddressableObjectHostShell.spec.tsx:L448-L451`.

E4. The refactor inventory counted the file at 761 lines and marked it as coverage for host shell, bridge, selection, panel, and anchors. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L68-L79`.

## 3. Proposed changes

### Change 1: Add new-name coverage first

Resolves Problem 2.

- Add `web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProvider.spec.tsx`.
- Import `AOLRuntimeShellProvider` and `AOLRuntimeShell`.
- Duplicate only the minimal shared-provider and opening-shell scenarios before changing production imports.

### Change 2: Split legacy spec by responsibility

Resolves Problem 1.

- Move provider/surface registration tests to `AOLRuntimeShellProvider.spec.tsx`.
- Move object selection and candidate role tests to `ObjectSelectionPanel.spec.tsx`.
- Move anchor/rail tests to `RuntimeShellAnchorRail.spec.tsx`.
- Move meeting pane mounting and title tests to `RuntimeShellPanel.spec.tsx`.
- Keep `AddressableObjectHostShell.spec.tsx` as compatibility alias coverage.

### Change 3: Rename semantics in assertions

Resolves Problem 3.

- Keep test ids stable for the first refactor.
- Update visible text assertions after production copy changes:
  - code shell: `AOLRuntimeShell`
  - product surface: `AOL Runtime Workbench`
  - meeting view: `Meeting Workbench`
  - debug only: `Meeting Graph`

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/AddressableObjectHostShell.spec.tsx --environment jsdom`
   Expected: old compatibility tests still pass.
   Fail: old imports or behavior break.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/aol-runtime-shell --environment jsdom`
   Expected: new-name shell tests pass.
   Fail: `AOLRuntimeShell` works only through old wrapper, not through new exports.

3. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "AddressableObjectHostShell|AOLRuntimeShell|aol-graph-shell-anchor|Meeting Workbench" web-console/src/components/capabilities`
   Expected: compatibility imports are explicit; new tests cover new names.
   Fail: only old names are tested.

## 5. Automated test plan

- `AOLRuntimeShellProvider.spec.tsx`: provider registration and shared shell state.
- `RuntimeShellPanel.spec.tsx`: meeting pane title, mount/unmount, size presets, close behavior.
- `RuntimeShellAnchorRail.spec.tsx`: select object anchor and open workbench anchor.
- `ObjectSelectionPanel.spec.tsx`: candidate picker, role control, selected object attach.
- Existing `AddressableObjectHostShell.spec.tsx`: compatibility alias smoke.

## 6. Risks / open questions

- Updating visible copy before splitting tests can make failures hard to locate. Split first, rename assertions second.
- Test ids with `graph-shell` may remain temporarily for compatibility.
- New tests should not overfit the temporary wrapper implementation.
