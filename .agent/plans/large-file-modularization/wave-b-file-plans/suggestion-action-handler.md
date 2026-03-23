# Suggestion Action Handler File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/suggestion_action_handler.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:28` defines `SuggestionActionHandler`.
- `:61` starts `handle_action()`.
- `:106` starts `handle_suggestion_action_with_ctx()`.
- `:177` starts `_handle_execute_playbook()`.
- `:265` starts `_handle_use_tool()`.
- `:344` starts `_handle_add_to_mindscape()`.
- `:1093` starts `_execute_via_plan()`.
- `:1135` starts `_create_user_event()`.
- Caller grep shows active compatibility usage: `suggestion_action_handler` = 5, `SuggestionAction` = 4.

## Phase 1.5: Historical Regression Analysis

- Commits `6671c7f`, `21763ac`, `56d0caa`, and `9b91069` added capability infra, execution chat behavior, async DB work, and PostgreSQL updates to this file.
- The file absorbed more action families instead of splitting by command type.

## Phase 2: Problem Definition + Severity Scoring

1. **Action-family overload**: playbook actions, tool actions, mindscape actions, plan execution, and event creation live together. Severity 5, Detection 4, Priority 20.
2. **Context coupling**: action routing and context-aware execution share one class. Severity 4, Detection 4, Priority 16.
3. **Shared action drift risk**: this file and `cta_handler.py` can diverge on similar behaviors. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: public callers mostly depend on the top-level handler, not internal helpers.
  Verification: grep footprint is on the module/handler, not private methods.
- Assumption: conversation execution tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_real_conversation.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_chat_endpoint_execution_plan.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_plan_flow.py` exist.

## Phase 3.5: Pre-Mortem

- Playbook and tool actions stop sharing the same permission checks.
- Event generation behavior drifts after extraction.
- Suggestion actions and CTA actions duplicate command routing.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/actions/`

Modules to create:
- `suggestion_handler.py`
- `action_router.py`
- `playbook_actions.py`
- `tool_actions.py`
- `mindscape_actions.py`
- `event_factory.py`

Implementation order:
1. Extract user-event creation and response shaping.
2. Extract playbook, tool, and mindscape action families into separate modules.
3. Extract `_execute_via_plan()` into shared execution support.
4. Add a small router layer that dispatches action type to the correct module.
5. Leave the old file as a facade exporting `SuggestionActionHandler`.

Do-not-miss checklist:
- [ ] `handle_action()` flow preserved
- [ ] context-aware entrypoint preserved
- [ ] playbook/tool/mindscape action families split
- [ ] plan execution helper shared
- [ ] user-event builder moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:28`
- `:61`
- `:106`
- `:177`
- `:265`
- `:344`
- `:1093`
- `:1135`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_real_conversation.py \
  backend/tests/test_chat_endpoint_execution_plan.py \
  backend/tests/test_execution_plan_flow.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a shared contract test if `SuggestionActionHandler` and `CTAHandler` start using common action modules.
- Add one regression per action family before deleting any duplicated helper.
