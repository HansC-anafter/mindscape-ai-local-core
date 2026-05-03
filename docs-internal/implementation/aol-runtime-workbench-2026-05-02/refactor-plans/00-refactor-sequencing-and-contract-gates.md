# AOL Runtime Shell Refactor Sequencing And Contract Gates

Target scope: first-stage refactor across the eight P0 files before the second-stage AOL Runtime Workbench UX/UI iteration.

## 1. Problem list

1. **The eight refactor files have local plans but no cross-file execution order**: frontend shell extraction, meeting workbench extraction, backend service split, meeting graph split, and model package conversion can block each other if implemented in parallel without gates. Evidence: E1, E2. Severity: 5. Detection: 4. Priority: 20.
2. **The first-stage refactor can accidentally become a UX rewrite**: the inventory explicitly says this pass should reorganize the implementation tree and perform the architecture rename, not redesign the end-user workbench experience. Evidence: E1. Severity: 4. Detection: 4. Priority: 16.
3. **The final product goal depends on a command ledger that is not currently implemented**: the UX can preview the workbench layout after refactor, but it cannot claim the meeting is the central collaboration platform until command rows are backend-ledger rows. Evidence: E3, E4. Severity: 5. Detection: 5. Priority: 25.
4. **Backend refactors have compatibility traps**: tests dynamically import route files and monkeypatch private helpers, while `backend.app.models.object_runtime` is currently a file import target that cannot coexist safely with an `object_runtime/` package. Evidence: E5, E6. Severity: 5. Detection: 5. Priority: 25.

## 2. Evidence

E1. The refactor inventory states this pass should reorganize the implementation tree and perform the architecture rename, and should not redesign the end-user workbench experience yet. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L7-L22`.

E2. The P0 refactor set contains eight local-core files spanning frontend shell, meeting bottom shell, specs, route page, object runtime route, meeting graph route, and object runtime models. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L70-L81`.

E3. The product UX/UI plan lists backend command ledger as a hard dependency for final UX and says direct-dispatch compatibility must not leak into product mode. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L546-L558`.

E4. The command-envelope plan says no implementation currently exists for `MeetingCommandEnvelope` or `MeetingCommandStore`, and P0 must add model, store, route, and graph join implementation. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L1-L14`.

E5. The object runtime route split plan records that backend tests dynamically load `object_runtime.py` and monkeypatch private helpers, and therefore route-level helper aliases must remain temporarily. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-plans/06-object-runtime-route-service-split-plan.md:L22-L24`, `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-plans/06-object-runtime-route-service-split-plan.md:L47-L50`.

E6. The object runtime model split plan records that `backend/app/models/object_runtime.py` must be converted deliberately because Python cannot safely keep both `object_runtime.py` and `object_runtime/` as the same import target. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-plans/08-object-runtime-model-split-plan.md:L7-L9`, `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-plans/08-object-runtime-model-split-plan.md:L31-L33`.

## 3. Proposed changes

### Change 1: Use compatibility-first frontend sequencing

Resolves Problems 1 and 2.

Execution order:

1. Add `web-console/src/components/capabilities/aol-runtime-shell/` with new shell exports.
2. Keep `AddressableObjectHostShell.tsx` as the compatibility facade until current callers and specs pass.
3. Rename product copy in the shell from `Meeting Graph` to `Meeting Workbench` only where it is the primary user-facing pane title.
4. Keep `Meeting Graph` copy available only for debug/provenance views.
5. Extract meeting workbench pure modules before replacing layout.
6. Keep `AOLMeetingBottomShell.tsx` as a compatibility wrapper until the extracted modules have direct tests.

### Change 2: Use contract-first backend sequencing

Resolves Problems 1 and 4.

Execution order:

1. Split backend service modules under new service directories without changing endpoint paths.
2. Preserve route-level aliases for existing tests that monkeypatch private helpers.
3. Keep response models and error codes stable while services are extracted.
4. Split `meeting_graph.py` projection code before changing the API response contract.
5. Convert `backend.app.models.object_runtime` from file to package only after import-compat tests pass.
6. Do not implement the command ledger in the same patch as the model package conversion.

### Change 3: Define hard product gates before second-stage UX

Resolves Problems 2 and 3.

The second-stage product UX/UI iteration cannot be called complete until:

- `POST /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands` exists.
- `GET /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands` exists.
- command rows have server-generated `command_id`.
- `Command Dock` submits a `MeetingCommandEnvelope`, not only direct `sendMessage(action_params)`.
- the workbench canvas projects backend command-ledger rows as authoritative command nodes.
- temporary direct-dispatch fallback is explicitly legacy/debug mode.

### Change 4: Keep implementation docs internal

Resolves Problem 1.

- Keep all 2026-05-02 implementation plans under `docs-internal/implementation/aol-runtime-workbench-2026-05-02/`.
- Public `docs/core-architecture/addressable-object-layer/` files may remain as architecture evidence sources.
- New implementation status docs for this work should be added under `docs-internal/implementation/aol-runtime-workbench-2026-05-02/`, not public core docs.

## 4. Verification SOP

1. **Internal document location**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && find docs/core-architecture/addressable-object-layer -maxdepth 2 \\( -name '*2026-05-02*.md' -o -name 'aol-runtime-shell-refactor-plans-2026-05-02' \\) -print`
   - Expected true: no implementation-plan files are present in public core architecture docs.
   - Fail false: any 2026-05-02 implementation plan appears under public core docs.

2. **No stale moved-plan references**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "docs/core-architecture/addressable-object-layer/(aol-runtime|meeting-command)" docs-internal/implementation/aol-runtime-workbench-2026-05-02`
   - Expected true: no moved implementation plan is referenced through the old public path.
   - Fail false: internal plans still point at old public implementation-plan paths.

3. **Frontend compatibility pass**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/AddressableObjectHostShell.spec.tsx src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx --environment jsdom`
   - Expected true: legacy callers still pass after compatibility exports and first extraction.
   - Fail false: host shell anchor, meeting pane, command submit, object graph, or session switch regresses.

4. **Backend contract pass**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/object_action_planning_runtime_test.py backend/tests/object_instance_registry_runtime_test.py backend/tests/test_object_meeting_attachment.py backend/tests/routes/core/test_workspace_object_runtime_api.py backend/tests/meeting_execution_graph_object_semantics_test.py`
   - Expected true: route contracts survive service extraction and model import compatibility.
   - Fail false: endpoint paths, response models, monkeypatch aliases, or import paths break.

## 5. Automated test plan

- Add shell compatibility tests before migrating app callers.
- Add direct tests for extracted meeting projection, mention parsing, object action payload construction, and runtime shell provider behavior.
- Add service-level backend tests only after route contract tests remain green.
- Add an import-compat test before converting `backend.app.models.object_runtime` into a package.
- Add command-ledger tests in a separate implementation phase, not inside the pure refactor phase.

## 6. Risks / open questions

- The first-stage refactor can create churn without product value if it changes UX before module boundaries are stable.
- The command ledger is the real product gate; without it, the meeting workbench remains a projection/preview layer.
- Backend package conversion is the riskiest single move and should be isolated.
- Current unrelated working-tree changes must not be reverted or mixed into this refactor.
