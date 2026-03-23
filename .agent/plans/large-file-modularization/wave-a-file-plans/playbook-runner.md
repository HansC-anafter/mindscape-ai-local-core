# Playbook Runner File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:215` defines `PlaybookRunner`.
- `:277` starts `start_playbook_execution()`.
- `:795` starts `continue_playbook_execution()`.
- `:1207` starts `get_playbook_execution_result()`.
- Helper cluster above the class builds run-state payloads and normalization behavior.
- Caller grep shows active compatibility usage: `PlaybookRunner` = 48, `playbook_runner` = 91.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `efef560`, `871027d`, `56d0caa`, `ac971b7` added execution, variant, async DB, and runtime behavior here.

## Phase 2: Problem Definition + Severity Scoring

1. **Lifecycle overload**: start, continue, result retrieval, and state-building live in one service. Severity 5, Detection 4, Priority 20.
2. **State payload duplication risk**: helper extraction is needed before later execution refactors. Severity 4, Detection 4, Priority 16.
3. **Very high caller footprint**: this path must remain stable. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: run-state builders can move without API changes.
  Verification: they are helpers, not public entrypoints.
- Assumption: runner tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_runner_routing.py` and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_runner_event_metadata.py` exist.

## Phase 3.5: Pre-Mortem

- Start/continue flows diverge after extraction.
- Run-state metadata changes silently.
- Facade becomes a second orchestration layer instead of a thin export.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/playbook_runner_core/`

Modules to create:
- `runner.py`
- `run_state.py`
- `start_flow.py`
- `continue_flow.py`
- `results.py`
- `normalization.py`

Implementation order:
1. Extract normalization and run-state helpers.
2. Extract start flow.
3. Extract continue flow.
4. Extract result/cleanup/list helpers.
5. Leave old module as facade exporting `PlaybookRunner`.

Do-not-miss checklist:
- [ ] run-state helpers extracted
- [ ] normalization helpers extracted
- [ ] start flow extracted
- [ ] continue flow extracted
- [ ] result retrieval extracted
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:215`
- `:277`
- `:795`
- `:1207`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_playbook_runner_routing.py \
  backend/tests/test_playbook_runner_event_metadata.py \
  backend/tests/test_runner_task_executor_events.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a facade import contract test plus a run-state payload snapshot test if extraction changes output assembly.
