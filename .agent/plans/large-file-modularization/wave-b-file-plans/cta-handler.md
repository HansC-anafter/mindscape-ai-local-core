# CTA Handler File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/cta_handler.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:36` defines `CTAHandler`.
- `:64` starts `handle_cta()`.
- `:294` starts `_handle_soft_write()`.
- `:492` starts `_handle_add_to_intents_direct()`.
- `:642` starts `_handle_external_write()`.
- `:868` starts `_execute_wordpress_publish()`.
- `:952` starts `_generate_confirmation()`.
- Caller grep shows active compatibility usage: `cta_handler` = 6.

## Phase 1.5: Historical Regression Analysis

- Commits `6671c7f`, `56d0caa`, `905f4d2`, and `8892905` added capability infra, async DB, CTA write paths, and publishing behavior in this file.
- More CTA families were layered into one handler instead of being moved to command modules.

## Phase 2: Problem Definition + Severity Scoring

1. **CTA-family overload**: soft write, direct intent updates, external writes, publishing, and confirmations live together. Severity 5, Detection 4, Priority 20.
2. **Confirmation coupling**: confirmation generation is mixed with stateful side-effect handlers. Severity 4, Detection 4, Priority 16.
3. **Action-layer duplication**: this file overlaps conceptually with `suggestion_action_handler.py`. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the public `CTAHandler` surface can stay stable while handlers move.
  Verification: internal CTA families are private helpers today.
- Assumption: conversation execution tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_real_conversation.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_chat_endpoint_execution_plan.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_plan_flow.py` exist.

## Phase 3.5: Pre-Mortem

- Confirmation text changes while moving side-effect handlers.
- External write and publishing behavior diverge.
- Shared action modules are copied instead of truly shared.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/actions/`

Modules to create:
- `cta_handler.py`
- `soft_write.py`
- `intent_updates.py`
- `external_write.py`
- `publishing.py`
- `confirmation.py`

Implementation order:
1. Extract confirmation builder into a pure module.
2. Extract soft-write and direct-intent handlers.
3. Extract external-write and publishing handlers.
4. Reuse shared action DTOs with `suggestion_action_handler.py`.
5. Leave the old file as a facade exporting `CTAHandler`.

Do-not-miss checklist:
- [ ] `handle_cta()` preserved
- [ ] soft-write path moved
- [ ] direct-intent path moved
- [ ] external-write path moved
- [ ] publishing path moved
- [ ] confirmation generation moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:36`
- `:64`
- `:294`
- `:492`
- `:642`
- `:868`
- `:952`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_real_conversation.py \
  backend/tests/test_chat_endpoint_execution_plan.py \
  backend/tests/test_execution_plan_flow.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a confirmation contract test before moving `_generate_confirmation()`.
- Add one regression per CTA family if shared action modules are introduced.
