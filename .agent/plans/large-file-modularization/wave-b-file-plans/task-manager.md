# Task Manager File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/task_manager.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:40` defines `TaskManager`.
- `:81` starts `create_timeline_item_from_task()`.
- `:492` starts `_create_graph_node_for_task()`.
- `:635` starts `_create_artifact_mind_event()`.
- `:979` starts `check_and_update_task_status()`.
- `:1168` starts `check_and_timeout_tasks()`.
- Caller grep shows active compatibility usage: `TaskManager` = 20, `task_manager` = 38.

## Phase 1.5: Historical Regression Analysis

- Commits `56d0caa`, `9b91069`, `6344c4b`, and `19dbe0a` expanded async DB work, PostgreSQL compatibility, scheduling, and task-event behavior in this file.
- Growth happened through task lifecycle accretion instead of boundary extraction.

## Phase 2: Problem Definition + Severity Scoring

1. **Lifecycle concentration**: timeline projection, graph nodes, artifact events, status updates, and timeout monitoring live together. Severity 5, Detection 4, Priority 20.
2. **Artifact side-effect coupling**: task state updates and artifact event emission are hard-wired in one module. Severity 4, Detection 4, Priority 16.
3. **Operational blast radius**: task scheduler and projection changes can regress together. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: helper clusters can move without changing public API.
  Verification: the stable surface is `TaskManager`; helper names are internal.
- Assumption: task and projection tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_task_execution_projection.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_task_scheduler_state.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_task_events_emitter.py` exist.

## Phase 3.5: Pre-Mortem

- Timeout and status-update paths diverge after extraction.
- Artifact events stop matching task-state transitions.
- Graph/timeline projection logic gets duplicated instead of centralized.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/tasks/`

Modules to create:
- `manager.py`
- `timeline_projection.py`
- `graph_projection.py`
- `artifact_events.py`
- `status_updates.py`
- `timeout_monitor.py`

Implementation order:
1. Extract timeline and graph projection helpers.
2. Extract artifact event builders and emitters.
3. Extract status-update logic.
4. Extract timeout-monitor loop and scheduling helpers.
5. Leave the old file as a facade exporting `TaskManager`.

Do-not-miss checklist:
- [ ] timeline projection moved
- [ ] graph node creation moved
- [ ] artifact event helpers moved
- [ ] status-update logic moved
- [ ] timeout logic moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:40`
- `:81`
- `:492`
- `:635`
- `:979`
- `:1168`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_task_execution_projection.py \
  backend/tests/test_task_scheduler_state.py \
  backend/tests/test_task_events_emitter.py \
  backend/tests/test_artifacts_phase0.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a facade import contract test if missing.
- Add a timeout-monitor regression test if extraction changes scheduler entrypoints.
