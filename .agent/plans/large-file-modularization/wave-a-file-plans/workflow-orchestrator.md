# Workflow Orchestrator File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:62` defines `WorkflowOrchestrator`.
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:454` starts `execute_workflow()`.
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:969` starts `_execute_playbook_steps()`.
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:1614` starts `_execute_single_step()`.
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:1997` starts `_execute_step_with_retry()`.
- Caller grep shows active compatibility usage: `WorkflowOrchestrator` = 14, `workflow_orchestrator` = 5.
- `git status --short` shows this file is already modified in the current worktree.

## Phase 1.5: Historical Regression Analysis

- Recent commits `42d1799`, `f7131ce`, `a2af848`, `b98ee2d`, `1afb88d` all added execution behavior into this file.
- The failure mode is additive growth, not missing helper functions.

## Phase 2: Problem Definition + Severity Scoring

1. **Core flow concentration**: orchestration, dependency resolution, remote routing, retries, and result projection live in one class. Severity 5, Detection 4, Priority 20.
2. **Retry and routing coupling**: remote-route and retry policy changes share the same file as core step execution. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: broad caller footprint means path changes without a facade will break imports. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: this file can become a facade.
  Verification: caller grep shows old path must stay, but implementation can move behind it.
- Assumption: workflow tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/test_workflow_orchestrator.py` and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workflow_orchestrator_remote_tool_routes.py` exist.

## Phase 3.5: Pre-Mortem

- Import cycles between new workflow modules and playbook runner.
- Async behavior drift in step execution/retry.
- Old file remains semi-fat instead of becoming a true facade.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/workflow/`

Modules to create:
- `orchestrator.py`
- `remote_route.py`
- `dependency_graph.py`
- `step_dispatch.py`
- `retry_policy.py`
- `result_mapper.py`

Implementation order:
1. Move `_utc_now()` to `backend/app/services/execution_core/clock.py`.
2. Move `RecoverableStepError` to `backend/app/services/execution_core/errors.py`.
3. Extract remote-route helpers.
4. Extract dependency graph and ready-step helpers.
5. Extract step dispatch and retry policy.
6. Extract final output/event mapping.
7. Rewrite old file as facade exporting `WorkflowOrchestrator` and `RecoverableStepError`.

Do-not-miss checklist:
- [ ] `execute_workflow()` body moved
- [ ] `_execute_playbook_steps()` moved
- [ ] `_execute_single_step()` and iteration helper moved
- [ ] retry helpers moved
- [ ] final output/event helpers moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:62`
- `:454`
- `:969`
- `:1614`
- `:1997`

## Phase 6: Validation SOP

```bash
pytest backend/tests/services/test_workflow_orchestrator.py \
  backend/tests/test_workflow_orchestrator_remote_tool_routes.py \
  backend/tests/test_execution_plan_flow.py
```

Pass:
- old import path still works
- workflow ordering/retry/remote route behavior unchanged

Fail:
- any caller import breaks
- retries or remote execution routing regress

## Phase 7: Evaluation & Automated Testing SOP

- Add a facade import contract test if missing.
- Add a fixed-clock retry-policy contract test if extraction changes helper boundaries.
