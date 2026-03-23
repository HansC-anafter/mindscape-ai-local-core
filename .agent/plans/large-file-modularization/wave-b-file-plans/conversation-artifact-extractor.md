# Conversation Artifact Extractor File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/conversation/artifact_extractor.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:27` defines another `ArtifactExtractor`.
- `:39` starts `extract_artifact_from_task_result()`.
- `:123`, `:316`, and `:515` repeat artifact-family extraction logic already present in the root extractor.
- Full-project grep found no live callers for `services.conversation.artifact_extractor` or `conversation.artifact_extractor`.
- `task_manager.py` imports the root extractor, not this file.

## Phase 1.5: Historical Regression Analysis

- Commits `56d0caa`, `fceb0b9`, and `5b1acc3` left this copy in place while the active root path kept evolving.
- The failure mode is duplicate survival, not active ownership.

## Phase 2: Problem Definition + Severity Scoring

1. **Dead duplicate risk**: a second extractor file can drift from the active implementation. Severity 5, Detection 4, Priority 20.
2. **False refactor surface**: engineers may patch the wrong file because names and symbols match. Severity 4, Detection 4, Priority 16.
3. **Migration ambiguity**: keeping both copies blocks clear canonical-path enforcement. Severity 5, Detection 3, Priority 15.

## Phase 3: Assumption Verification

- Assumption: this file has no runtime callers.
  Verification: grep over the repo found no active imports of this module path.
- Assumption: removal can happen after the canonical extractor is established.
  Verification: the real active path is the root extractor today, which will first become a shim to the new canonical package.

## Phase 3.5: Pre-Mortem

- Someone updates this file again during refactor because the name looks valid.
- The file is removed before the canonical package exists.
- Documentation still points here after code migration finishes.

## Phase 4: Plan Writing

Target state:
- Archive and remove after canonicalization under `backend/app/services/conversation/artifacts/`

Modules to create:
- No new modules from this file directly.
- Replace this file with either a short deprecation shim or remove it entirely in the final cleanup commit.

Implementation order:
1. Establish canonical extractor under `conversation/artifacts/`.
2. Convert the root extractor to a shim.
3. Re-run full-project grep for this conversation-path import.
4. Delete this file, or leave a minimal deprecation shim for one short migration window.
5. Update docs and references to the canonical package only.

Do-not-miss checklist:
- [ ] canonical extractor package exists
- [ ] root shim exists before deletion
- [ ] repo grep confirms zero callers
- [ ] docs updated away from this path
- [ ] file archived or removed in cleanup commit

## Phase 5: Citation Audit

Re-verify before coding:
- `:27`
- `:39`
- `:123`
- `:316`
- `:515`

## Phase 6: Validation SOP

```bash
rg -n "services\\.conversation\\.artifact_extractor|conversation\\.artifact_extractor" \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core
pytest backend/tests/test_artifacts_phase0.py \
  backend/tests/test_artifacts_route.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a repo-level grep check in the cleanup PR description before deletion.
- Do not ship deletion until the canonical extractor tests pass from the new package path.
