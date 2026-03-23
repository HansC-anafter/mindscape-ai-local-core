# Tool Registry File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_registry.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:55` defines `ToolRegistryService`.
- `:74` starts `__init__()`.
- `:118` starts `_ensure_tables()`.
- `:140` starts `_load_registry()`.
- `:1354` starts `get_tools_for_agent_role()`.
- `:1393` starts `_infer_side_effect_level()`.
- `:1451` starts `discover_wordpress_capabilities()`.
- Caller grep shows active compatibility usage: `ToolRegistryService` = 136, `tool_registry` = 271.

## Phase 1.5: Historical Regression Analysis

- Commits `b98ee2d`, `1afb88d`, `e496827`, and `3507077` expanded registry loading, embeddings, tooling policies, and discovery behavior in this file.
- Registry responsibilities kept accreting rather than splitting into store, discovery, and resolver layers.

## Phase 2: Problem Definition + Severity Scoring

1. **Registry overload**: table bootstrap, registry load, policy inference, role filtering, and capability discovery live in one service. Severity 5, Detection 4, Priority 20.
2. **Very high caller footprint**: this module path is widely depended on and must remain stable during migration. Severity 5, Detection 3, Priority 15.
3. **Policy/discovery coupling**: search and side-effect inference changes are too tightly linked. Severity 4, Detection 4, Priority 16.

## Phase 3: Assumption Verification

- Assumption: the old module must become a facade rather than disappear.
  Verification: caller counts show broad import dependence.
- Assumption: registry-focused tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_rag_cache.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_rag_recall.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_category_alias.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_filtered_tools_playbook_service_cache.py` exist.

## Phase 3.5: Pre-Mortem

- Registry load order changes after extraction.
- Policy inference logic drifts from tool discovery results.
- The new package creates cycles with embedding or playbook services.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/registry/`

Modules to create:
- `service.py`
- `registry_store.py`
- `discovery.py`
- `role_filtering.py`
- `policy_inference.py`
- `wordpress_bridge.py`

Implementation order:
1. Extract policy inference and role filtering into pure modules.
2. Extract discovery and WordPress capability bridging.
3. Extract registry load/store concerns.
4. Move the main coordinator into `service.py`.
5. Leave the old module as a facade exporting `ToolRegistryService`.

Do-not-miss checklist:
- [ ] table/bootstrap logic moved
- [ ] registry load/store moved
- [ ] role filtering moved
- [ ] side-effect inference moved
- [ ] capability discovery moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:55`
- `:74`
- `:118`
- `:140`
- `:1354`
- `:1393`
- `:1451`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_tool_rag_cache.py \
  backend/tests/test_tool_rag_recall.py \
  backend/tests/test_tool_category_alias.py \
  backend/tests/test_filtered_tools_playbook_service_cache.py \
  backend/tests/test_tool_policy_resolver_fallback.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a facade import contract test if missing.
- Add a registry load-order regression test before moving `_load_registry()`.
