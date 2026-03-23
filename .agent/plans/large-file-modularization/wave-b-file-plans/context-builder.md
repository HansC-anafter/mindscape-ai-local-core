# Context Builder File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/context_builder/builder.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:27` defines `ContextBuilder`.
- `:73` starts `build_qa_context()`.
- `:242` starts `_build_layered_memory_context()`.
- `:306` starts `_build_workspace_metadata_context()`.
- `:327` starts `_build_active_intents_context()`.
- `:357` starts `_build_current_tasks_context()`.
- `:430` starts `_build_recent_files_context()`.
- `:692` starts `build_planning_context()`.
- `:968` starts `build_enhanced_prompt()`.
- Caller grep shows active compatibility usage: `ContextBuilder` = 44, `context_builder.builder` = 1.

## Phase 1.5: Historical Regression Analysis

- Commits `75b362b`, `21763ac`, and `4d32f50` expanded memory layering, execution chat context, and prompt-construction behavior in this file.
- Context collectors accumulated in one builder instead of being split into providers.

## Phase 2: Problem Definition + Severity Scoring

1. **Collector concentration**: memory, workspace metadata, intents, tasks, files, planning, and prompt assembly live in one builder. Severity 5, Detection 4, Priority 20.
2. **Budgeting ambiguity**: context gathering and final prompt assembly are not cleanly separated. Severity 4, Detection 4, Priority 16.
3. **High caller footprint**: the public builder path must stay stable. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: collectors can move into submodules while keeping the builder interface.
  Verification: callers target `ContextBuilder`; internal collectors are private methods.
- Assumption: prompt-context tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_prompt_builder_runtime_profile_injection.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_real_conversation.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_chat_endpoint_execution_plan.py` exist.

## Phase 3.5: Pre-Mortem

- Prompt token budgeting changes after extraction.
- One collector stops being included in planning context.
- The new package still routes every call through a giant builder method.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/context/`

Modules to create:
- `builder.py`
- `memory_layers.py`
- `workspace_metadata.py`
- `intent_context.py`
- `task_context.py`
- `recent_files.py`
- `planning_context.py`
- `prompt_assembler.py`

Implementation order:
1. Extract collectors into one module per context family.
2. Extract prompt assembly and budgeting helpers.
3. Move `build_qa_context()` and `build_planning_context()` into the new builder.
4. Leave the old file as a facade exporting `ContextBuilder`.

Do-not-miss checklist:
- [ ] memory collector moved
- [ ] workspace metadata collector moved
- [ ] intent/task/file collectors moved
- [ ] planning-context builder moved
- [ ] prompt assembler moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:27`
- `:73`
- `:242`
- `:306`
- `:327`
- `:357`
- `:430`
- `:692`
- `:968`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_prompt_builder_runtime_profile_injection.py \
  backend/tests/test_real_conversation.py \
  backend/tests/test_chat_endpoint_execution_plan.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add per-collector regression tests if the extraction changes inclusion order.
- Add a facade import contract test if builder callers rely on the old module path.
