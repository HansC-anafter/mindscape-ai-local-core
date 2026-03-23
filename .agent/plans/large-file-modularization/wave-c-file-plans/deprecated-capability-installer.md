# Deprecated Capability Installer File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/deprecated/capability_installer.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:40` defines `CapabilityInstaller`.
- `:73` starts `install_from_mindpack()`.
- `:178` starts `_validate_manifest()`.
- `:261` starts `_install_capability()`.
- `:352` starts `_validate_installed_playbooks()`.
- `:576` starts `_check_dependencies()`.
- `:1642` starts `_run_post_install_hooks()`.
- `:1693` starts `_bootstrap_content_vault()`.
- `:1743` starts `_run_python_script()`.
- `deprecated/__init__.py` explicitly labels this module as the old unified installer replaced by modular installers.
- Runtime grep found no live backend or script callers for `CapabilityInstaller(` or the deprecated module path.

## Phase 1.5: Historical Regression Analysis

- Commits `b98ee2d`, `6671c7f`, and `850e60c` show this file was the old expansion point before modular installers split out.
- The current risk is legacy survival, not missing new helper extraction.

## Phase 2: Problem Definition + Severity Scoring

1. **False refactor target**: this file looks active but is structurally deprecated. Severity 5, Detection 4, Priority 20.
2. **Legacy resurrection risk**: engineers may keep adding behavior here instead of the modular installers. Severity 5, Detection 4, Priority 20.
3. **Docs/runtime ambiguity**: references left behind can create uncertainty about the real install path. Severity 4, Detection 4, Priority 16.

## Phase 3: Assumption Verification

- Assumption: this file is not an active runtime dependency.
  Verification: repo grep over `backend/` and `scripts/` found no live runtime callers.
- Assumption: active installer tests exist elsewhere.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_assets_installer.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_pack_hygiene.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_no_legacy_playbook_apis.py` exist.

## Phase 3.5: Pre-Mortem

- A refactor accidentally ports old behavior back into active paths.
- The file is deleted before docs and references are redirected.
- Deprecated imports survive in hidden scripts because grep scope was incomplete.

## Phase 4: Plan Writing

Target state:
- Archive or remove after docs/reference cleanup

Modules to create:
- No new modules should be extracted from this file.
- If a short compatibility surface is required, replace this file with a minimal deprecation shim only.

Implementation order:
1. Reconfirm zero runtime callers with repo grep.
2. Update docs and comments to point at `playbook_installer.py` and other modular installers.
3. Decide whether a one-release deprecation shim is needed.
4. Archive or delete the file in a cleanup commit.

Do-not-miss checklist:
- [ ] runtime grep rerun
- [ ] docs/reference cleanup completed
- [ ] no new code extracted from this file
- [ ] cleanup commit isolates removal from active installer changes

## Phase 5: Citation Audit

Re-verify before coding:
- `:40`
- `:73`
- `:178`
- `:261`
- `:352`
- `:576`
- `:1642`
- `:1693`
- `:1743`

## Phase 6: Validation SOP

```bash
rg -n "CapabilityInstaller\\(|services\\.deprecated\\.capability_installer" \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/scripts
pytest backend/tests/test_runtime_assets_installer.py \
  backend/tests/test_runtime_pack_hygiene.py \
  backend/tests/test_no_legacy_playbook_apis.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Do not mix archival cleanup with active installer refactors in one commit.
- Add a docs note or deprecation shim only if hidden callers appear during the final grep.
