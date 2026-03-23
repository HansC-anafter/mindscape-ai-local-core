# Decision Coordinator File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:236` defines `UnifiedDecisionCoordinator`.
- `:298` starts `make_unified_decision()`.
- `:432` starts `_synthesize_decision()`.
- `:683` starts `_store_decision_to_intent_log()`.
- `:1133` starts `_record_governance_decisions()`.
- The file also holds DTO/contract classes above the coordinator.
- Caller grep shows active compatibility usage: `UnifiedDecisionCoordinator` = 11, `decision.coordinator` = 19.

## Phase 1.5: Historical Regression Analysis

- Commits `e496827`, `56d0caa`, `4d32f50`, `64ad7dd`, `6344c4b` kept landing decision, event-stream, and DB migration work here.

## Phase 2: Problem Definition + Severity Scoring

1. **DTO and orchestration colocation**: contracts and synthesis logic are mixed in one file. Severity 4, Detection 4, Priority 16.
2. **Persistence and event emission coupling**: storage and emission live beside decision synthesis. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: public coordinator path must remain stable. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: DTOs can move out first.
  Verification: caller interest is in coordinator/class path, not file-local DTO placement.
- Assumption: coordinator tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_coordinator_facade_integration.py` exists.

## Phase 3.5: Pre-Mortem

- DTO extraction causes import churn across decision callers.
- Persistence/event helpers still leak back into coordinator shell.
- Approval logic changes subtly because serialization moved with the wrong dependencies.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/decision/core/`

Modules to create:
- `contracts.py`
- `coordinator.py`
- `synthesis.py`
- `policies.py`
- `persistence.py`
- `serialization.py`
- `events.py`

Implementation order:
1. Move DTO/contracts.
2. Move serialization helpers.
3. Move synthesis/conflict logic.
4. Move persistence and events.
5. Leave old file as thin facade exporting coordinator and contracts.

Do-not-miss checklist:
- [ ] DTOs extracted
- [ ] synthesis extracted
- [ ] policies extracted
- [ ] persistence extracted
- [ ] events extracted
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:236`
- `:298`
- `:432`
- `:683`
- `:1133`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_coordinator_facade_integration.py \
  backend/tests/test_chat_endpoint_execution_plan.py \
  backend/tests/test_execution_metadata_governance.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a contract test asserting coordinator facade imports and emitted governance payload shape stay stable.
