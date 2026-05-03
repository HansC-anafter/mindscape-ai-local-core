# Object Runtime Route Service Split Refactor Plan

Target file: `backend/app/routes/core/workspace/object_runtime.py`

## 1. Problem list

1. **The route file is a 2774-line service and route hybrid**: imports, singleton stores, validators, catalog conversion, planner logic, materialization logic, meeting attach logic, graph projection, and route handlers live together. Evidence: E1, E2, E3, E4. Severity: 5. Detection: 4. Priority: 20.
2. **Route handlers own business behavior that the AOL Runtime Shell needs as stable services**: object action planning/invocation, meeting attach, materialization, and graph projection are backend runtime boundaries, but they are not isolated behind service modules. Evidence: E3, E4. Severity: 5. Detection: 4. Priority: 20.
3. **Existing tests dynamically import this route file and monkeypatch private helpers**: a refactor without compatibility helpers would break backend tests and hide behavior changes. Evidence: E5. Severity: 4. Detection: 5. Priority: 20.
4. **Endpoint paths must remain stable for local-core UI and pack compatibility**: frontend and tests call `/objects/complete`, `/object-actions/plan`, `/object-actions/invoke`, `/object-meeting-attach`, `/object-materialize`, and `/object-graph/project`. Evidence: E4, E6. Severity: 5. Detection: 5. Priority: 25.

## 2. Evidence

E1. The file imports a large set of object runtime models and stores, declares module-level singleton store variables, and defines store getter helpers. Source: `backend/app/routes/core/workspace/object_runtime.py:L1-L139`.

E2. Catalog/ref helper functions such as `_to_catalog_entry`, `_build_object_ref`, and `_parse_mindscape_uri` are in the route file. Source: `backend/app/routes/core/workspace/object_runtime.py:L147-L220`.

E3. Route-local helper groups include action planning/invocation, materialization, meeting attachment metadata, relation normalization, and graph projection resolution. Source: `backend/app/routes/core/workspace/object_runtime.py:L369-L1680`.

E4. Route handlers for catalog, index, sync, relation search, object search/read/complete, action plan/invoke/close, selection resolve, meeting attach, materialize, and graph project are in this one file. Source: `backend/app/routes/core/workspace/object_runtime.py:L1747-L2774`.

E5. Backend tests dynamically load `object_runtime.py` and monkeypatch private helpers in multiple files. Source: `backend/tests/object_action_planning_runtime_test.py:L31-L49`, `backend/tests/object_instance_registry_runtime_test.py:L30-L48`, `backend/tests/test_object_meeting_attachment.py:L30-L48`, `backend/tests/routes/core/test_workspace_object_runtime_api.py:L27-L47`.

E6. Frontend Meeting Workbench currently calls object runtime endpoints for `/objects/sync`, `/objects/complete`, `/object-actions/plan`, `/object-actions/invoke`, and `/object-graph/project`. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L3076-L4129`.

## 3. Proposed changes

### Change 1: Create service modules without changing routes

Resolves Problems 1, 2, and 4.

- Add `backend/app/services/object_runtime/`.
- Extract:
  - `catalog_service.py`
  - `selection_service.py`
  - `action_planner.py`
  - `action_invoker.py`
  - `meeting_attachment_service.py`
  - `materialization_service.py`
  - `graph_projection_service.py`
- Keep `backend/app/routes/core/workspace/object_runtime.py` as the FastAPI route owner.

### Change 2: Move store access behind service dependencies

Resolves Problems 1 and 2.

- Move singleton store getters into a service dependency module.
- Keep route-level helper aliases temporarily for tests that monkeypatch private helpers.
- Do not introduce dependency injection changes in the same patch unless tests are updated.

### Change 3: Thin route handlers

Resolves Problems 1, 2, and 4.

- Each route should validate workspace, call the corresponding service, and return the existing response model.
- Endpoint paths and response models must remain unchanged.
- Preserve current error codes where tests or UI depend on them:
  - `object_kind_not_declared`
  - `action_plan_id_required`
  - `role_assignments_required`
  - `selected_affordance_required`
  - `materializer_unavailable`
  - `object_not_found`

### Change 4: Compatibility test migration

Resolves Problem 3.

- First update tests to import service modules for direct behavior where possible.
- Keep route dynamic-import tests as route contract tests only.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/object_action_planning_runtime_test.py backend/tests/object_instance_registry_runtime_test.py backend/tests/test_object_meeting_attachment.py backend/tests/test_aol_target_only_attach.py backend/tests/routes/core/test_workspace_object_runtime_api.py -q`
   Expected: route contracts and service behavior remain stable.
   Fail: object action, graph projection, attach, or object registry tests fail.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "async def .*workspace|@router\\.|def _get_" backend/app/routes/core/workspace/object_runtime.py backend/app/services/object_runtime`
   Expected: route file has route handlers; service modules own business helpers.
   Fail: the route still owns all extracted logic.

3. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "/object-actions/plan|/object-actions/invoke|/object-graph/project|/object-meeting-attach" backend/app/routes/core/workspace/object_runtime.py web-console/src`
   Expected: endpoint paths are unchanged.
   Fail: UI or API route paths drift.

## 5. Automated test plan

- Add `backend/tests/services/object_runtime/test_action_planner.py`.
  Scenario: supported, needs disambiguation, unsupported, planner backend failure.
  Prevents: Problem 2.

- Add `backend/tests/services/object_runtime/test_action_invoker.py`.
  Scenario: invoke planned action, require `action_plan_id`, persist task, close output relations.
  Prevents: Problems 2 and 4.

- Add `backend/tests/services/object_runtime/test_graph_projection_service.py`.
  Scenario: owner-pack graph projection plus persisted relation registry projection.
  Prevents: Problems 2 and 4.

- Keep `backend/tests/routes/core/test_workspace_object_runtime_api.py` as endpoint contract coverage.

## 6. Risks / open questions

- Dynamic test imports currently depend on private route helpers; migrate tests gradually.
- Do not change endpoint paths or response model imports during service extraction.
- Service splitting can introduce circular imports with `object_action_closure_wiring`; keep import direction route -> service -> models/stores.
