# Playbook Registry File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_registry.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:42` defines `PlaybookRegistry`.
- `:48` starts `__init__()`.
- `:96` starts `_ensure_loaded()`.
- `:155` starts `_load_all_playbooks()`.
- `:1338` starts `get_variant()`.
- `:1354` starts `list_variants()`.
- `:1366` starts `get_playbook_registry()`.
- Caller grep shows active compatibility usage: `PlaybookRegistry` = 71, `playbook_registry` = 10.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `56253af`, `bbac226`, and `44eb233` added runtime loading, variant resolution, and execution-path integration into this file.
- The registry became both cache loader and query service.

## Phase 2: Problem Definition + Severity Scoring

1. **Loader/query concentration**: load-all, cache readiness, variant selection, and factory wiring live together. Severity 4, Detection 4, Priority 16.
2. **Compatibility sensitivity**: many callers expect the current registry path and factory function. Severity 5, Detection 3, Priority 15.
3. **Variant-resolution fragility**: changes to load order and query helpers can silently affect playbook selection. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the module should become a facade rather than a deleted path.
  Verification: caller footprint is high enough that import stability matters.
- Assumption: playbook/pack hygiene tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_pack_hygiene.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_pack_activation_state.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_no_legacy_playbook_apis.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_invocation_strategy.py` exist.

## Phase 3.5: Pre-Mortem

- Load cache invalidation changes after extraction.
- Variant lookup returns different defaults.
- Factory helper and singleton behavior diverge.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/playbook_registry/`

Modules to create:
- `registry.py`
- `manifest_loader.py`
- `cache.py`
- `variant_resolution.py`
- `query_service.py`
- `factory.py`

Implementation order:
1. Extract variant-resolution helpers.
2. Extract manifest loading and cache readiness logic.
3. Move public query helpers into `query_service.py`.
4. Move factory/singleton helpers into `factory.py`.
5. Leave the old module as a facade exporting `PlaybookRegistry` and `get_playbook_registry()`.

Do-not-miss checklist:
- [ ] cache readiness logic moved
- [ ] load-all logic moved
- [ ] variant helpers moved
- [ ] factory helper moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:42`
- `:48`
- `:96`
- `:155`
- `:1338`
- `:1354`
- `:1366`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_runtime_pack_hygiene.py \
  backend/tests/test_pack_activation_state.py \
  backend/tests/test_no_legacy_playbook_apis.py \
  backend/tests/test_playbook_invocation_strategy.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a facade import contract test if missing.
- Add a variant-resolution snapshot or matrix test before changing cache/load order.
