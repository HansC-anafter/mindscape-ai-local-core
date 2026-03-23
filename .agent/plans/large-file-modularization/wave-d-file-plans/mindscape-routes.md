# Mindscape Feature Routes File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/mindscape/routes.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:39` defines `SelfIntroRequest`.
- `:47` starts `get_onboarding_status()`.
- `:134` starts `playbook_completion_webhook()`.
- `:166` starts `create_profile()`.
- `:188` starts `get_profile()`.
- `:1141` starts `tag_entity()`.
- `:1155` starts `untag_entity()`.
- `:1172` starts `get_entities_by_tag()`.
- Caller grep shows active compatibility usage: `mindscape.routes` = 11, `get_entities_by_tag` = 8.

## Phase 1.5: Historical Regression Analysis

- Commits `442386e`, `2761d68`, `c34f8c9`, and `8892905` added onboarding, webhook, profile, and tagging behavior here.
- Multiple endpoint families accumulated in one feature route file.

## Phase 2: Problem Definition + Severity Scoring

1. **Endpoint-family concentration**: onboarding, webhook, profile, and tag-management handlers live together. Severity 4, Detection 4, Priority 16.
2. **Schema/handler mixing**: request models and route logic are not separated. Severity 4, Detection 4, Priority 16.
3. **Feature-growth risk**: future mindscape endpoints will likely keep landing in this file unless explicit package seams are created. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the current route module can become a package facade.
  Verification: route imports are path-sensitive, but handler families are separable.
- Assumption: relevant feature tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_intent_api_workspace_isolation.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_intent_workspace_isolation_strict.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_dashboard.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_running_server_routes.py` exist.

## Phase 3.5: Pre-Mortem

- Webhook auth or payload parsing changes while schemas move.
- Tagging endpoints drift from profile or onboarding dependencies.
- The router export changes and breaks feature registration.

## Phase 4: Plan Writing

Target package:
- `backend/features/mindscape/routes/`

Modules to create:
- `router.py`
- `schemas.py`
- `onboarding.py`
- `webhooks.py`
- `profile.py`
- `tagging.py`

Implementation order:
1. Extract schemas and shared dependencies.
2. Extract onboarding and profile handlers.
3. Extract webhook handler family.
4. Extract tagging handlers.
5. Leave the old file as a facade re-exporting the router object.

Do-not-miss checklist:
- [ ] schemas moved
- [ ] onboarding/profile handlers split
- [ ] webhook handler split
- [ ] tagging handlers split
- [ ] router export preserved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:39`
- `:47`
- `:134`
- `:166`
- `:188`
- `:1141`
- `:1155`
- `:1172`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_intent_api_workspace_isolation.py \
  backend/tests/test_intent_workspace_isolation_strict.py \
  backend/tests/test_dashboard.py \
  backend/tests/test_running_server_routes.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a router import contract test if missing.
- Add focused webhook and tagging regressions before deleting any shared helpers.
