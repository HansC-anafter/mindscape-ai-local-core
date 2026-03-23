# Conversation Manager File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/conversation_manager.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:17` defines `PlaybookConversationManager`.
- `:59` starts `build_system_prompt()`.
- `:307` starts `get_messages_for_llm()`.
- `:320` starts `extract_structured_output()`.
- `:941` starts `add_tool_call_results()`.
- `:1022` starts `to_dict()`.
- `:1042` starts `from_dict()`.
- Caller grep shows active compatibility usage: `PlaybookConversationManager` = 13, `conversation_manager` = 9.

## Phase 1.5: Historical Regression Analysis

- Commits `4d32f50`, `64ad7dd`, `375e4ae`, and `4f211f1` grew prompt construction, message handling, serialization, and tool-call result behavior in this file.
- The file became both prompt builder and conversation-state serializer.

## Phase 2: Problem Definition + Severity Scoring

1. **State and prompt coupling**: system prompt building, message assembly, structured-output parsing, and serialization live together. Severity 4, Detection 4, Priority 16.
2. **Tool-result overload**: tool call result merging sits in the same module as persistence DTOs. Severity 4, Detection 4, Priority 16.
3. **Conversation drift risk**: prompt changes can affect serialization behavior in the same refactor. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the manager can be reassembled from smaller collaborators without changing the public class.
  Verification: callers use the manager abstraction and serialization helpers, not the internal prompt helpers directly.
- Assumption: conversation and execution-context tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_real_conversation.py` and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_executor_meeting_context.py` exist.

## Phase 3.5: Pre-Mortem

- Prompt text assembly changes while moving serialization helpers.
- Tool-call result ordering changes.
- The new package splits responsibilities but duplicates DTO logic.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/playbook/conversation/`

Modules to create:
- `manager.py`
- `system_prompt.py`
- `message_projection.py`
- `structured_output.py`
- `tool_results.py`
- `serialization.py`

Implementation order:
1. Extract serialization helpers.
2. Extract system prompt builder.
3. Extract message projection and structured-output parsing.
4. Extract tool-call result merging.
5. Leave the old file as a facade exporting `PlaybookConversationManager`.

Do-not-miss checklist:
- [ ] system prompt builder moved
- [ ] message projection moved
- [ ] structured-output parser moved
- [ ] tool-result merge moved
- [ ] serialization moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:17`
- `:59`
- `:307`
- `:320`
- `:941`
- `:1022`
- `:1042`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_real_conversation.py \
  backend/tests/test_playbook_executor_meeting_context.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a serialization round-trip test before moving `to_dict()` and `from_dict()`.
- Add a prompt snapshot test if `build_system_prompt()` moves across modules.
