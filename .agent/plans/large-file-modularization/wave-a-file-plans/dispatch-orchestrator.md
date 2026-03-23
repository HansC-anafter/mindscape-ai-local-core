# Dispatch Orchestrator File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:34` defines `DispatchOrchestrator`.
- `:93` starts `execute()`.
- `:318` starts `_dispatch_phase()`.
- `:524` starts `_launch_playbook()`.
- `:646` starts `_dispatch_tool()`.
- Caller grep shows active compatibility usage: `DispatchOrchestrator` = 20, `dispatch_orchestrator` = 2.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `442386e`, `643e19f`, `1afb88d`, `56253af` kept adding dispatch behavior, callback handling, and supporting-service integration here.

## Phase 2: Problem Definition + Severity Scoring

1. **Topology and side-effect overload**: DAG traversal and side-effectful dispatch live in one file. Severity 4, Detection 4, Priority 16.
2. **Attempt/provenance coupling**: state tracking and provenance assembly live beside dispatch execution. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: public orchestrator path must remain stable. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: attempts/topology can move before playbook/tool dispatch.
  Verification: they are helper concerns with no public surface.
- Assumption: dispatch tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_dispatch_orchestrator.py` exists.

## Phase 3.5: Pre-Mortem

- Phase walk order changes after topology extraction.
- Attempt records stop matching dispatch events.
- Old file keeps both orchestration and helper logic.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/orchestration/dispatch/`

Modules to create:
- `orchestrator.py`
- `phase_dispatch.py`
- `playbook_launch.py`
- `tool_dispatch.py`
- `attempts.py`
- `topology.py`
- `provenance.py`
- `activity.py`

Implementation order:
1. Extract attempts and topology helpers.
2. Extract provenance helpers.
3. Extract activity publishing.
4. Extract playbook and tool dispatch.
5. Leave old file as facade exporting `DispatchOrchestrator`.

Do-not-miss checklist:
- [ ] topology extracted
- [ ] attempts extracted
- [ ] provenance extracted
- [ ] activity publishing extracted
- [ ] playbook launch extracted
- [ ] tool dispatch extracted
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:34`
- `:93`
- `:318`
- `:524`
- `:646`

## Phase 6: Validation SOP

```bash
pytest backend/tests/services/orchestration/test_dispatch_orchestrator.py \
  backend/tests/services/orchestration/test_dispatch_orchestrator_idempotency.py \
  backend/tests/services/orchestration/test_dispatch_policy_gate.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a dispatch-attempt contract test if extraction changes ordering or provenance fields.
