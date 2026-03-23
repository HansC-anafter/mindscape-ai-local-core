# Playbook Installer File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_installer.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:21` defines `PlaybookInstaller`.
- `:24` starts `_install_playbooks()`.
- `:101` starts `_validate_playbook_required_fields()`.
- `:193` starts `_validate_tools_direct_call()`.
- `:250` starts `get_backend_from_manifest()`.
- Caller grep shows active compatibility usage: `PlaybookInstaller` = 7, `playbook_installer` = 18.
- File header already says it was extracted from `capability_installer.py`.

## Phase 1.5: Historical Regression Analysis

- Commits `b98ee2d`, `6671c7f`, `205b625`, and `e9d6e5f` show the file is already a partial extraction from the legacy installer.
- The next step is finishing the split, not growing this file into another monolith.

## Phase 2: Problem Definition + Severity Scoring

1. **Partial-extraction stall**: validation, manifest logic, and install flow still live together in one file. Severity 4, Detection 4, Priority 16.
2. **Legacy rebound risk**: without further modularization, this file can become the new unified installer. Severity 4, Detection 4, Priority 16.
3. **Manifest-policy coupling**: backend resolution and direct-call validation are too close to install execution. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: this is an active installer and should be modularized, not archived.
  Verification: file header positions it as the extracted replacement from the deprecated installer.
- Assumption: relevant pack/playbook tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_pack_hygiene.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_no_legacy_playbook_apis.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_invocation_strategy.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_pack_activation_state.py` exist.

## Phase 3.5: Pre-Mortem

- Manifest validation changes after extraction.
- Backend resolution behavior drifts.
- The new installer modules still leak direct-call policy into execution code.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/installers/playbooks/`

Modules to create:
- `installer.py`
- `manifest_validation.py`
- `tool_validation.py`
- `backend_resolution.py`
- `reporting.py`

Implementation order:
1. Extract manifest required-field validation.
2. Extract direct-call tool validation.
3. Extract backend resolution helpers.
4. Move the main installer flow to `installer.py`.
5. Leave the old file as a facade exporting `PlaybookInstaller`.

Do-not-miss checklist:
- [ ] `_install_playbooks()` moved
- [ ] required-field validation moved
- [ ] direct-call validation moved
- [ ] backend resolution moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:21`
- `:24`
- `:101`
- `:193`
- `:250`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_runtime_pack_hygiene.py \
  backend/tests/test_no_legacy_playbook_apis.py \
  backend/tests/test_playbook_invocation_strategy.py \
  backend/tests/test_pack_activation_state.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a backend-resolution contract test before moving `get_backend_from_manifest()`.
- Add a facade import contract test if callers rely on the old module path.
