# Meeting Graph Route Projection Split Refactor Plan

Target file: `backend/app/routes/core/workspace/meeting_graph.py`

## 1. Problem list

1. **The route file owns models, projection helpers, graph builder, event merge, store lookups, and FastAPI route in one 912-line file**. Evidence: E1, E2, E3, E4. Severity: 4. Detection: 4. Priority: 16.
2. **Meeting graph is runtime/debug substrate but is currently coupled to route naming and implementation lanes**: response models expose graph lanes and node kinds directly from the route module. Evidence: E1, E2. Severity: 4. Detection: 3. Priority: 12.
3. **Existing tests import `build_meeting_execution_graph` from this route module**: moving projection logic without compatibility exports can break graph semantics tests. Evidence: E5. Severity: 4. Detection: 5. Priority: 20.

## 2. Evidence

E1. `meeting_graph.py` declares `MeetingExecutionGraphNode`, `MeetingExecutionGraphEdge`, and `MeetingExecutionGraphResponse` in the route module. Source: `backend/app/routes/core/workspace/meeting_graph.py:L27-L69`.

E2. Helper functions for string coercion, IDs, task status, object refs, relation payloads, and fallback nodes live in the same route module. Source: `backend/app/routes/core/workspace/meeting_graph.py:L75-L304`.

E3. `_build_task_graph_nodes` and `build_meeting_execution_graph` construct command, run, closure, output object, relation, and artifact nodes. Source: `backend/app/routes/core/workspace/meeting_graph.py:L305-L725`.

E4. `merge_meeting_event_runtime_projection`, `_bounded_graph_lookup`, and `get_meeting_execution_graph` route handler are in the same module. Source: `backend/app/routes/core/workspace/meeting_graph.py:L807-L912`.

E5. `backend/tests/meeting_execution_graph_object_semantics_test.py` dynamically loads `meeting_graph.py` and reads `build_meeting_execution_graph` from it. Source: `backend/tests/meeting_execution_graph_object_semantics_test.py:L20-L42`.

## 3. Proposed changes

### Change 1: Move response models to `backend/app/models/meeting_graph.py`

Resolves Problems 1 and 2.

- Move `MeetingExecutionGraphNode`, `MeetingExecutionGraphEdge`, and `MeetingExecutionGraphResponse`.
- Keep field names unchanged.
- Keep lanes unchanged as debug/runtime substrate for this phase.

### Change 2: Move projection builder into service modules

Resolves Problems 1 and 2.

- Add `backend/app/services/meeting_graph/projection_builder.py` for:
  - coercion helpers
  - `_build_task_graph_nodes`
  - `build_meeting_execution_graph`
- Add `backend/app/services/meeting_graph/event_projection.py` for:
  - `_event_runtime_node`
  - `merge_meeting_event_runtime_projection`
- Keep behavior identical.

### Change 3: Thin the route

Resolves Problem 1.

- `backend/app/routes/core/workspace/meeting_graph.py` should own only:
  - router declaration
  - dependencies
  - bounded lookup helper if route-specific
  - `get_meeting_execution_graph`
- The route should call service builders and return `MeetingExecutionGraphResponse`.

### Change 4: Compatibility export during migration

Resolves Problem 3.

- Re-export `build_meeting_execution_graph` from the route module temporarily.
- Update tests to import from `backend.app.services.meeting_graph.projection_builder` after the service is stable.

## 4. Verification SOP

1. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python -m pytest backend/tests/meeting_execution_graph_object_semantics_test.py -q`
   Expected: graph semantics remain stable.
   Fail: command/run/closure/relation/artifact node semantics change.

2. Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "class MeetingExecutionGraph|def build_meeting_execution_graph|def merge_meeting_event_runtime_projection|@router.get" backend/app/models backend/app/services/meeting_graph backend/app/routes/core/workspace/meeting_graph.py`
   Expected: models and builders live outside the route; route keeps endpoint.
   Fail: route remains the only owner.

3. API check: `curl -sS "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/execution-graph?limit=10" | jq '.nodes, .edges'`
   Expected: response still includes `nodes` and `edges`.
   Fail: endpoint path or response shape changes.

## 5. Automated test plan

- Add `backend/tests/services/meeting_graph/test_projection_builder.py`.
  Scenario: task with object action plan, closure, output ref, persisted relations, and artifact.
  Assertions: command/run/output/provenance nodes and edges match existing semantics.
  Prevents: Problems 1 and 2.

- Add `backend/tests/services/meeting_graph/test_event_projection.py`.
  Scenario: meeting events merge into graph with sequential `then` edges.
  Assertions: duplicate node/edge suppression works.
  Prevents: Problem 1.

- Keep route test or add one API-level test for `/meetings/{meeting_id}/execution-graph`.

## 6. Risks / open questions

- Do not rename `MeetingExecutionGraph*` yet; these are runtime/debug substrate names.
- Existing dynamic import tests should be migrated after temporary re-export lands.
- Store lookup timeout behavior belongs near route/dependency code unless reused by other services.
