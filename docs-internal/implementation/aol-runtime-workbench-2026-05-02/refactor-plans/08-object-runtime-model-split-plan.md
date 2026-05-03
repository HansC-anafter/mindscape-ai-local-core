# Object Runtime Model Split Refactor Plan

Target file: `backend/app/models/object_runtime.py`

## 1. Problem list

1. **The 833-line model file combines every Addressable Object Layer transport domain**: selectors, refs, summaries, catalog, instance index, selection resolve, meeting attach, materialization, object actions, relation records, closure, and graph projection are all in one module. Evidence: E1, E2, E3. Severity: 4. Detection: 4. Priority: 16.
2. **Backend routes and tests import many models from the single module**: splitting the file incorrectly can break import compatibility across route and test modules. Evidence: E4, E5. Severity: 5. Detection: 5. Priority: 25.
3. **The target package name conflicts with the existing file path**: converting `backend.app.models.object_runtime` from a file to a package requires a deliberate move because Python cannot keep `object_runtime.py` and `object_runtime/` as the same import target safely. Evidence: E6. Severity: 4. Detection: 5. Priority: 20.

## 2. Evidence

E1. The file starts with selector models and `ObjectRef`, `ObjectSummary`, `ObjectAction`, resolver/capability/catalog models. Source: `backend/app/models/object_runtime.py:L1-L220`.

E2. Meeting attach, materialization, action plan/invoke, relation, closure, and graph projection models are defined in the same file. Source: `backend/app/models/object_runtime.py:L526-L833`.

E3. The refactor inventory counted this file at 833 lines and proposed splitting models by API surface: refs/catalog, selection, actions, meeting attach/materialize, graph projection. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L68-L79`.

E4. `backend/app/routes/core/workspace/object_runtime.py` imports object runtime models from `....models.object_runtime` in one large import block. Source: `backend/app/routes/core/workspace/object_runtime.py:L15-L58`.

E5. Tests import `ObjectRef`, `ObjectMeetingAttachRequest`, `ObjectCatalogEntry`, selectors, object action models, and relation/graph models from `backend.app.models.object_runtime`. Source: `backend/tests/object_catalog_registry_aol_contracts_test.py:L8`, `backend/tests/test_aol_target_only_attach.py:L7`, `backend/tests/object_runtime_selectors_test.py:L11`, `backend/tests/object_action_planning_runtime_test.py:L19-L49`, `backend/tests/object_instance_registry_runtime_test.py:L19-L48`.

E6. Current file path is `backend/app/models/object_runtime.py`; the inventory target tree proposes `backend/app/models/object_runtime/` with split modules and `__init__.py`. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-shell-refactor-inventory-2026-05-02.md:L151-L160`.

## 3. Proposed changes

### Change 1: Convert the module into a compatibility package

Resolves Problems 2 and 3.

- Move `backend/app/models/object_runtime.py` to `backend/app/models/object_runtime/__init__.py`.
- Keep `from backend.app.models.object_runtime import ObjectRef` working.
- Do not leave both `object_runtime.py` and `object_runtime/` in place.

### Change 2: Split model domains into submodules

Resolves Problem 1.

- Add:
  - `refs.py`: selector models, `ObjectRef`, `ObjectSummary`
  - `catalog.py`: resolver/capability/catalog models
  - `selection.py`: selection surface/hints/resolve models
  - `actions.py`: action, affordance, plan, invoke, closure models
  - `meeting.py`: role entries, meeting attach request/response
  - `materialization.py`: materialize request/response
  - `graph.py`: relation records and graph projection request/response
  - `instance_index.py`: instance index/search/read/mention models
- `__init__.py` should re-export all public names currently imported by routes/tests.

### Change 3: Preserve validation behavior

Resolves Problems 1 and 2.

- Keep selector validation behavior exactly as-is.
- Keep legacy coercers on `ObjectMeetingAttachRequest` and `ObjectMaterializeRequest`.
- Keep `ConfigDict(extra="forbid")` on existing models.

### Change 4: Update imports only after package re-export passes

Resolves Problem 2.

- First patch: package conversion plus re-exports, no consumer import changes required.
- Second patch: optionally update internal routes/services to import from submodules for clarity.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/object_runtime_selectors_test.py backend/tests/object_catalog_registry_aol_contracts_test.py backend/tests/object_action_planning_runtime_test.py backend/tests/object_instance_registry_runtime_test.py backend/tests/test_aol_target_only_attach.py backend/tests/test_object_meeting_attachment.py -q`
   Expected: model validation and route helper tests still import from `backend.app.models.object_runtime`.
   Fail: import errors or model validation differences.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python - <<'PY'\nfrom backend.app.models.object_runtime import ObjectRef, ObjectMeetingAttachRequest, ObjectGraphProjectRequest\nprint(ObjectRef.__name__, ObjectMeetingAttachRequest.__name__, ObjectGraphProjectRequest.__name__)\nPY`
   Expected: imports work through package `__init__.py`.
   Fail: any import error.

3. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "object_runtime.py|models/object_runtime/" backend/app/models backend/app/routes backend/tests`
   Expected: no stale file/package conflict and imports remain intentional.
   Fail: both file and package coexist or consumers import missing modules.

## 5. Automated test plan

- Keep existing selector tests for `ObjectRef.selector`.
- Add `backend/tests/models/object_runtime/test_import_compat.py`.
  Scenario: import all public model names from `backend.app.models.object_runtime`.
  Assertions: imports succeed and model class names match.
  Prevents: Problems 2 and 3.

- Add `backend/tests/models/object_runtime/test_legacy_payload_coercion.py`.
  Scenario: legacy `objects` / `target_ref` and `context_objects` payloads.
  Assertions: normalized `entries` and `context_entries` match existing behavior.
  Prevents: Problem 1.

## 6. Risks / open questions

- Python module-to-package conversion is a larger move than normal file splitting; do it in a dedicated patch.
- Consumer imports should remain stable through `__init__.py` re-exports.
- Avoid changing model field names during this phase; command ledger models should be added separately.
