# Playbook Run Executor File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:117` defines `PlaybookRunExecutor`.
- `:163` starts `execute_playbook_run()`.
- `:842` starts `_maybe_dispatch_remote_execution()`.
- `:939` starts `_handle_standalone()`.
- `:1220` starts `_execute_workflow_legacy()`.
- Caller grep shows active compatibility usage: `PlaybookRunExecutor` = 30, `playbook_run_executor` = 18.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `442386e`, `643e19f`, `a2af848`, `56253af` kept adding remote dispatch, callbacks, stabilization, and support logic here.

## Phase 2: Problem Definition + Severity Scoring

1. **Execution mode overload**: standalone, plan-node, remote, and legacy paths are mixed in one file. Severity 5, Detection 4, Priority 20.
2. **Dispatch fallback ambiguity**: remote dispatch and legacy fallback live too close together. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: high caller count requires facade preservation. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: package split can happen without changing public class name.
  Verification: callers target class/module path, not internal helpers.
- Assumption: execution tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_executor_meeting_context.py` and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_runner_metadata.py` exist.

## Phase 3.5: Pre-Mortem

- Remote callback path breaks because helper extraction moves imports incorrectly.
- Legacy path keeps hidden coupling to the old module.
- Public executor remains a fat file after extraction.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/playbook_run/`

Modules to create:
- `executor.py`
- `dispatch.py`
- `standalone.py`
- `plan_node.py`
- `legacy_workflow.py`
- `runtime_loader.py`
- `error_policy.py`

Implementation order:
1. Extract runtime/error helpers.
2. Extract remote dispatch helper set.
3. Extract standalone flow.
4. Extract plan-node flow.
5. Extract legacy workflow flow.
6. Leave old file as public facade exporting `PlaybookRunExecutor`.

Do-not-miss checklist:
- [ ] remote dispatch extracted
- [ ] standalone flow extracted
- [ ] plan-node flow extracted
- [ ] legacy workflow extracted
- [ ] runtime provider loading extracted
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:117`
- `:163`
- `:842`
- `:939`
- `:1220`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_playbook_executor_meeting_context.py \
  backend/tests/test_execution_runner_metadata.py \
  backend/tests/test_execution_chat_agent_service.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a contract test covering remote-dispatch chosen vs legacy fallback chosen for the same executor facade.
