# Runtime Assets Installer File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/runtime_assets_installer.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:20` defines `RuntimeAssetsInstaller`.
- `:35` starts `install_all()`.
- `:101` starts `install_workflows()`.
- `:120` starts `install_tools()`.
- `:155` starts `install_services()`.
- `:190` starts `install_jobs()`.
- `:216` starts `install_api_endpoints()`.
- `:1281` starts `install_root_files()`.
- `:1312` starts `install_docs()`.
- `:1332` starts `install_evals()`.
- Caller grep shows active compatibility usage: `RuntimeAssetsInstaller` = 9, `runtime_assets_installer` = 6.

## Phase 1.5: Historical Regression Analysis

- Commits `872fb8e`, `e85ace9`, `b606e71`, and `86951c0` added more install surfaces rather than extracting per-asset installers.
- The file became a long step pipeline without clear phase modules.

## Phase 2: Problem Definition + Severity Scoring

1. **Installer-step overload**: workflows, tools, services, jobs, APIs, root files, docs, and evals live in one class. Severity 5, Detection 4, Priority 20.
2. **Validation/side-effect coupling**: install sequencing and write operations are mixed together. Severity 4, Detection 4, Priority 16.
3. **Rollback ambiguity**: failures across multiple install families are hard to localize. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: this file should remain the compatibility facade while modules move below it.
  Verification: caller footprint is moderate but real.
- Assumption: installer tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_assets_installer.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_pack_hygiene.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_app_bootstrap.py` exist.

## Phase 3.5: Pre-Mortem

- Install order changes after extraction.
- One asset family gets skipped because the pipeline split is incomplete.
- Validation and rollback responsibilities stay scattered.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/installers/runtime_assets/`

Modules to create:
- `installer.py`
- `install_plan.py`
- `workflow_assets.py`
- `tool_assets.py`
- `service_assets.py`
- `job_assets.py`
- `api_assets.py`
- `root_assets.py`
- `docs_assets.py`
- `eval_assets.py`

Implementation order:
1. Extract one asset-family module at a time in current execution order.
2. Extract shared install-plan and validation helpers.
3. Extract rollback/reporting helpers if the file already simulates them.
4. Leave the old module as a facade exporting `RuntimeAssetsInstaller`.

Do-not-miss checklist:
- [ ] `install_all()` sequencing preserved
- [ ] workflows/tools/services/jobs split
- [ ] API/root/docs/evals split
- [ ] shared validation helpers isolated
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:20`
- `:35`
- `:101`
- `:120`
- `:155`
- `:190`
- `:216`
- `:1281`
- `:1312`
- `:1332`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_runtime_assets_installer.py \
  backend/tests/test_runtime_pack_hygiene.py \
  backend/tests/test_app_bootstrap.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a sequencing contract test before moving `install_all()`.
- Add one regression per asset family if extraction changes install order or skip conditions.
