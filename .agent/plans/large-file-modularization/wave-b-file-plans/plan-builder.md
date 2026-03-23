# Plan Builder File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/plan_builder.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:34` defines `PlanBuilder`.
- `:72` starts `_select_model_for_plan()`.
- `:221` starts `_ensure_external_backend_loaded()`.
- `:447` starts `_generate_llm_plan()`.
- `:1189` starts `generate_execution_plan()`.
- `:1472` starts `_get_pack_id_from_playbook_code()`.
- Caller grep shows active compatibility usage: `PlanBuilder` = 20, `plan_builder` = 35.

## Phase 1.5: Historical Regression Analysis

- Commits `6671c7f`, `3683884`, `56d0caa`, and `9b91069` added capability infra, fail-loud dispatch behavior, async DB work, and PostgreSQL adaptation here.
- The file became the default insertion point for planning, backend loading, and model-selection changes.

## Phase 2: Problem Definition + Severity Scoring

1. **Planning overload**: model selection, pack resolution, backend loading, LLM generation, and trace logging live in one class. Severity 5, Detection 4, Priority 20.
2. **External backend coupling**: loading external backends is mixed into plan generation logic, so failures are hard to isolate. Severity 4, Detection 4, Priority 16.
3. **Broad caller footprint**: import stability must hold while internals move. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: the old module can become a facade.
  Verification: callers target `PlanBuilder`, not helper functions.
- Assumption: execution-plan tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_chat_endpoint_execution_plan.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_plan_flow.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_invocation_strategy.py` exist.

## Phase 3.5: Pre-Mortem

- Model-selection drift after extraction changes plan quality.
- Backend loading and pack lookup split across multiple incomplete seams.
- Old file keeps orchestration logic instead of becoming a thin export.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/planning/`

Modules to create:
- `builder.py`
- `model_selection.py`
- `backend_loader.py`
- `llm_plan_generator.py`
- `pack_resolution.py`
- `trace_logging.py`

Implementation order:
1. Extract pack lookup and model-selection helpers.
2. Extract external-backend loading into its own adapter boundary.
3. Extract LLM plan generation and response normalization.
4. Move execution-plan assembly into `builder.py`.
5. Rewrite the old file as a facade exporting `PlanBuilder`.

Do-not-miss checklist:
- [ ] `_select_model_for_plan()` moved
- [ ] `_ensure_external_backend_loaded()` moved
- [ ] `_generate_llm_plan()` moved
- [ ] plan assembly moved
- [ ] trace logging isolated
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:34`
- `:72`
- `:221`
- `:447`
- `:1189`
- `:1472`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_chat_endpoint_execution_plan.py \
  backend/tests/test_execution_plan_flow.py \
  backend/tests/test_playbook_invocation_strategy.py \
  backend/tests/test_prompt_builder_runtime_profile_injection.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a facade import contract test if missing.
- Add a model-selection contract test before moving provider fallback logic.
