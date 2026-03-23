# Workspace Tools File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tools/workspace_tools.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:45` defines `WorkspaceGetExecutionTool`.
- `:67` starts the first `execute()` implementation.
- `:85` defines `WorkspaceGetExecutionStepsTool`.
- `:107` starts the next `execute()` implementation.
- `:903` starts the final tool-family `execute()` cluster.
- `:983` starts `create_workspace_tools()`.
- `:998` starts `get_workspace_tool_by_name()`.
- Caller grep shows active compatibility usage: `workspace_tools` = 244, `MindscapeTool` = 259.

## Phase 1.5: Historical Regression Analysis

- Commits `d243d82`, `6671c7f`, `c296be8`, and `423f5bf` added more workspace tool families and registry behavior here.
- Tool definitions and factory wiring kept piling into one file.

## Phase 2: Problem Definition + Severity Scoring

1. **Tool-family concentration**: many workspace tools plus factory functions live in one file. Severity 5, Detection 4, Priority 20.
2. **High compatibility sensitivity**: factory helpers and module path are widely used. Severity 5, Detection 3, Priority 15.
3. **Serializer/guard duplication risk**: path guards and response shaping can drift across tool classes. Severity 4, Detection 4, Priority 16.

## Phase 3: Assumption Verification

- Assumption: the module must remain as a facade during migration.
  Verification: caller footprint is broad.
- Assumption: workspace tool tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workspace_execution_tools.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_chat_tool_catalog.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_category_alias.py` exist.

## Phase 3.5: Pre-Mortem

- Tool registration order changes after per-file extraction.
- Shared serializers/guards diverge between tool classes.
- Factory lookup no longer returns the same tool set.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/tools/workspace/`

Modules to create:
- `execution_tools.py`
- `step_tools.py`
- `artifacts_tools.py`
- `shared_guards.py`
- `serializers.py`
- `factory.py`

Implementation order:
1. Group tools by domain and move each family to its own module.
2. Extract shared guards and serializers.
3. Move `create_workspace_tools()` and `get_workspace_tool_by_name()` into `factory.py`.
4. Leave the old module as a facade re-exporting the same factories and tool classes.

Do-not-miss checklist:
- [ ] tool-family grouping defined
- [ ] shared guards extracted
- [ ] serializers extracted
- [ ] factory helpers moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:45`
- `:67`
- `:85`
- `:107`
- `:903`
- `:983`
- `:998`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_workspace_execution_tools.py \
  backend/tests/test_execution_chat_tool_catalog.py \
  backend/tests/test_tool_category_alias.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a factory output snapshot test before moving `create_workspace_tools()`.
- Add one regression per tool family if shared serializers or guards move.
