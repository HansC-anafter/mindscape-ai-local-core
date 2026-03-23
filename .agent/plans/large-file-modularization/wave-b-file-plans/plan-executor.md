# Plan Executor File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_executor.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:24` defines `PlanExecutor`.
- `:62` starts `execute_plan()`.
- `:726` starts `_determine_auto_execute()`.
- `:796` starts `_execute_readonly_task()`.
- `:993` starts `_handle_execution_failure()`.
- `:1046` starts `_handle_soft_write_task()`.
- Caller grep shows active compatibility usage: `PlanExecutor` = 3, `plan_executor` = 4.

## Phase 1.5: Historical Regression Analysis

- Commits `56253af`, `21763ac`, `e496827`, and `e190672` added execution routing, chat behavior, and planning fallback logic into this file.
- Behavior kept accumulating around task mode branches.

## Phase 2: Problem Definition + Severity Scoring

1. **Execution-mode concentration**: readonly, soft-write, auto-execute, and failure handling live in one class. Severity 5, Detection 4, Priority 20.
2. **Policy and execution coupling**: auto-execute decisions are mixed with task execution side effects. Severity 4, Detection 4, Priority 16.
3. **Low-visibility regressions**: few direct callers means behavior drift can hide behind integration tests only. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: this file can become a facade without changing callers.
  Verification: caller footprint is small and centered on the public class.
- Assumption: plan-execution tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_plan_flow.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_chat_endpoint_execution_plan.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_invocation_strategy.py` exist.

## Phase 3.5: Pre-Mortem

- Auto-execute rules change during extraction.
- Soft-write and readonly tasks stop sharing failure mapping.
- The new package reintroduces conditional sprawl under different filenames.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/execution/`

Modules to create:
- `executor.py`
- `auto_execute_policy.py`
- `readonly_tasks.py`
- `soft_write_tasks.py`
- `failure_mapper.py`

Implementation order:
1. Extract auto-execute policy into a pure decision module.
2. Extract readonly-task execution.
3. Extract soft-write-task execution.
4. Extract failure mapping and retry/notification helpers.
5. Leave the old file as a facade exporting `PlanExecutor`.

Do-not-miss checklist:
- [ ] `execute_plan()` preserved
- [ ] auto-execute policy moved
- [ ] readonly path moved
- [ ] soft-write path moved
- [ ] failure handling moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:24`
- `:62`
- `:726`
- `:796`
- `:993`
- `:1046`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_execution_plan_flow.py \
  backend/tests/test_chat_endpoint_execution_plan.py \
  backend/tests/test_playbook_invocation_strategy.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a contract test for `_determine_auto_execute()` behavior once moved to a pure module.
- Add one failure-mapping regression test before collapsing old helpers.
