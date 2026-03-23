# Governance Engine File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:32` defines `GovernanceEngine`.
- `:100` starts `process_completion()`.
- `:430` starts `process_playbook_webhook()`.
- `:600` starts `_invoke_legacy_webhook_handler()`.
- `:977` starts follow-up task logic.
- Caller grep shows active compatibility usage: `GovernanceEngine` = 25, `governance_engine` = 8.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799` and `442386e` pushed execution chat and unified governance/callback handling into this file.

## Phase 2: Problem Definition + Severity Scoring

1. **Ingress + persistence overload**: completion ingress, webhook handling, provenance, and follow-up logic are co-located. Severity 4, Detection 4, Priority 16.
2. **Legacy bridge coupling**: old webhook bridge is mixed with current orchestration path. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: active callers require path stability. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: provenance/follow-up helpers can move first.
  Verification: they are private helper blocks with no separate public surface.
- Assumption: governance tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_governance_engine_unified.py` exists.

## Phase 3.5: Pre-Mortem

- Extracted provenance helpers lose access to shared store/adapter state.
- Legacy webhook bridge breaks current callback path.
- Follow-up generation drifts because helper order changes.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/orchestration/governance/`

Modules to create:
- `engine.py`
- `completion_ingress.py`
- `webhook_bridge.py`
- `artifact_metadata.py`
- `provenance.py`
- `follow_up.py`

Implementation order:
1. Extract provenance and eval summary helpers.
2. Extract follow-up helper block.
3. Extract webhook bridge.
4. Extract ingress handlers.
5. Leave old file as public facade shell.

Do-not-miss checklist:
- [ ] provenance helpers extracted
- [ ] eval summary helpers extracted
- [ ] webhook bridge extracted
- [ ] follow-up helpers extracted
- [ ] artifact metadata helpers extracted
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:32`
- `:100`
- `:430`
- `:600`
- `:977`

## Phase 6: Validation SOP

```bash
pytest backend/tests/services/orchestration/test_governance_engine_unified.py \
  backend/tests/services/orchestration/test_governance_engine_governance_payload.py \
  backend/tests/services/orchestration/test_governance_provenance_backfill.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a follow-up creation contract test if helper extraction changes task emission order.
