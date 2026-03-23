# Meeting Engine File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:86` defines `MeetingEngine`.
- `:275` starts `run()`.
- `:435` starts deliberation stage.
- `:705` starts decompose-and-dispatch stage.
- `:886` starts finalize stage.
- Caller grep shows active compatibility usage: `MeetingEngine` = 29, `orchestration.meeting.engine` = 1.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `442386e`, `643e19f`, `1afb88d`, `3a92d10` kept pushing runtime, callback, and persona/stage complexity into this file.

## Phase 2: Problem Definition + Severity Scoring

1. **Stage overload**: agenda, contract, deliberation, dispatch, and finalize stages live in one file. Severity 4, Detection 4, Priority 16.
2. **Runtime helper coupling**: infra/store adapters and stage execution are mixed. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: public engine path must stay stable. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: stage bodies can move behind the same class.
  Verification: callers target `MeetingEngine`, not file-local stage method locations.
- Assumption: meeting tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_meeting_v6.py` and `test_meeting_supervisor.py` exist.

## Phase 3.5: Pre-Mortem

- Stage ordering changes accidentally during extraction.
- Supervisor and dispatch stage share hidden local state.
- Engine shell keeps too much behavior and remains large.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/orchestration/meeting/runtime/`

Modules to create:
- `engine.py`
- `contracts.py`
- `agenda_stage.py`
- `contract_stage.py`
- `deliberation_stage.py`
- `dispatch_stage.py`
- `finalize.py`
- `infra.py`

Implementation order:
1. Move contracts and infra helpers.
2. Extract agenda and contract stages.
3. Extract deliberation stage and supervisor logic.
4. Extract dispatch stage.
5. Extract finalize stage.
6. Leave old file as coordinator shell only.

Do-not-miss checklist:
- [ ] contracts extracted
- [ ] all stage bodies extracted
- [ ] infra helpers extracted
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:86`
- `:275`
- `:435`
- `:705`
- `:886`

## Phase 6: Validation SOP

```bash
pytest backend/tests/services/orchestration/test_meeting_v6.py \
  backend/tests/services/orchestration/test_meeting_supervisor.py \
  backend/tests/services/orchestration/test_meeting_dispatch.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a stage-order contract test if extraction moves the main `run()` flow.
