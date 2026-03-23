# Playbook Execution Routes File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:41` starts `_safe_screenshot_basename()`.
- `:63` starts `get_execution_debug_screenshot()`.
- `:90` starts `start_playbook_execution()`.
- `:442` starts `continue_playbook_execution()`.
- `:468` starts `get_playbook_result()`.
- `:581` starts `get_playbook_status()`.
- `:933` starts `list_active_executions()`.
- `:942` starts `reindex_playbooks_for_executor()`.
- `:961` starts `get_global_executions()`.
- Caller grep shows active compatibility usage: `playbook_execution` = 187, `start_playbook_execution` = 13.

## Phase 1.5: Historical Regression Analysis

- Commits `04cdf83`, `442386e`, `643e19f`, and `f4a302d` added pack activation, callback bridge behavior, governance dispatch, and queue-position support here.
- HTTP transport and execution orchestration kept landing in the same route file.

## Phase 2: Problem Definition + Severity Scoring

1. **Route-surface overload**: start/continue/result/status/list/reindex/debug handlers live in one module. Severity 5, Detection 4, Priority 20.
2. **Transport/orchestration coupling**: HTTP parsing, file serving, queue behavior, and execution dispatch are intertwined. Severity 5, Detection 4, Priority 20.
3. **High compatibility sensitivity**: this route surface is broadly referenced and should keep a stable router export. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: the current module path must remain as a router facade.
  Verification: caller footprint is broad and route imports are path-sensitive.
- Assumption: route/execution tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_api_execution_coordinator.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_queue_position_cache.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_running_server_routes.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_chat_agent_service.py` exist.

## Phase 3.5: Pre-Mortem

- Router registration changes after extraction.
- Start/continue handlers diverge in validation or auth behavior.
- Debug screenshot serving breaks because helper paths move without tests.

## Phase 4: Plan Writing

Target package:
- `backend/app/routes/core/playbook_execution/`

Modules to create:
- `router.py`
- `schemas.py`
- `dependencies.py`
- `handlers/start.py`
- `handlers/control.py`
- `handlers/debug.py`
- `response_mappers.py`
- `screenshot_utils.py`

Implementation order:
1. Extract schemas and shared dependencies.
2. Extract screenshot/debug helpers.
3. Split start/continue handlers from read/status/list handlers.
4. Extract response mapping and queue/result projection helpers.
5. Leave the old file as a facade re-exporting the router object.

Do-not-miss checklist:
- [ ] router export preserved
- [ ] start/continue handlers split
- [ ] result/status/list handlers split
- [ ] debug screenshot helpers moved
- [ ] response mapping moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:41`
- `:63`
- `:90`
- `:442`
- `:468`
- `:581`
- `:933`
- `:942`
- `:961`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_api_execution_coordinator.py \
  backend/tests/test_queue_position_cache.py \
  backend/tests/test_running_server_routes.py \
  backend/tests/test_execution_chat_agent_service.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a router import contract test if missing.
- Add focused debug-screenshot route coverage before moving `get_execution_debug_screenshot()`.
