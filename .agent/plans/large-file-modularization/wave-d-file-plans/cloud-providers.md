# Cloud Providers Routes File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/cloud_providers.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:22` defines `ProviderConfig`.
- `:30` defines `ProviderResponse`.
- `:41` defines `ProviderAction`.
- `:67` defines `TestConnectionResponse`.
- `:74` starts `get_settings_store()`.
- `:79` starts `get_cloud_manager()`.
- `:119` starts `list_providers()`.
- `:769` starts `_get_packs_catalog()`.
- `:905` starts `_parse_action_required()`.
- `:933` starts `_create_provider_instance()`.
- Caller grep shows active compatibility usage: `cloud_providers` = 19, `ProviderConfig` = 5.

## Phase 1.5: Historical Regression Analysis

- Commits `6671c7f`, `e496827`, `e14318a`, and `95943d6` added capability infra, provider runtime changes, and action-required behavior here.
- Schemas, settings access, catalog loading, and provider factory behavior kept accumulating in one file.

## Phase 2: Problem Definition + Severity Scoring

1. **Schema/factory/handler mixing**: provider DTOs, settings access, provider creation, catalog logic, and handlers live together. Severity 4, Detection 4, Priority 16.
2. **Provider instantiation fragility**: `_create_provider_instance()` is too close to HTTP-layer parsing. Severity 4, Detection 4, Priority 16.
3. **Action-required parsing risk**: transport-specific parsing and provider semantics are coupled. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the route path should remain stable while implementation moves into a package.
  Verification: route modules are import-sensitive and should keep the same facade path.
- Assumption: provider/runtime-profile tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_running_server_routes.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workspace_runtime_profile.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_profile_e2e.py` exist.

## Phase 3.5: Pre-Mortem

- Provider factory changes while schemas are moved.
- Action-required parsing drifts from runtime-profile behavior.
- Catalog loading still leaks into handlers after extraction.

## Phase 4: Plan Writing

Target package:
- `backend/app/routes/core/cloud_providers/`

Modules to create:
- `router.py`
- `schemas.py`
- `settings_store.py`
- `cloud_manager.py`
- `provider_factory.py`
- `packs_catalog.py`
- `handlers.py`

Implementation order:
1. Extract schemas first.
2. Extract settings-store and cloud-manager dependencies.
3. Extract provider factory and action-required parsing.
4. Extract pack-catalog helpers.
5. Leave the old file as a facade re-exporting the router object.

Do-not-miss checklist:
- [ ] schemas moved
- [ ] settings and manager providers moved
- [ ] provider factory moved
- [ ] pack-catalog helpers moved
- [ ] router export preserved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:22`
- `:30`
- `:41`
- `:67`
- `:74`
- `:79`
- `:119`
- `:769`
- `:905`
- `:933`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_running_server_routes.py \
  backend/tests/test_workspace_runtime_profile.py \
  backend/tests/test_runtime_profile_e2e.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a provider-factory contract test before moving `_create_provider_instance()`.
- Add an action-required parser regression test if schemas and handlers split in the same PR.
