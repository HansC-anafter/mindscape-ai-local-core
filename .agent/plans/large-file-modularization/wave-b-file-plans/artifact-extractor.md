# Artifact Extractor File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/artifact_extractor.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:27` defines `ArtifactExtractor`.
- `:39` starts `extract_artifact_from_task_result()`.
- `:123` starts `_extract_daily_planning_artifact()`.
- `:316` starts `_extract_content_drafting_artifact()`.
- `:515` starts `_extract_major_proposal_artifact()`.
- `:1332` starts `_check_file_conflict()`.
- `:1413` starts `_extract_version_from_filename()`.
- Caller grep shows active compatibility usage: `ArtifactExtractor` = 8, `artifact_extractor` = 14.

## Phase 1.5: Historical Regression Analysis

- Commits `56d0caa`, `f37ba9d`, and `19dbe0a` added async DB changes, artifact coverage, and event flow behavior here.
- This is the active extractor path used by task management.

## Phase 2: Problem Definition + Severity Scoring

1. **Rule concentration**: multiple artifact families, conflict checks, versioning, and file-output policy live in one class. Severity 5, Detection 4, Priority 20.
2. **Canonical-path ambiguity**: root extractor and conversation copy both exist, which raises split-brain risk. Severity 5, Detection 4, Priority 20.
3. **Side-effect coupling**: detection logic and write/conflict behavior are not isolated. Severity 4, Detection 4, Priority 16.

## Phase 3: Assumption Verification

- Assumption: this should become the temporary compatibility shim, not the long-term canonical location.
  Verification: the master plan defines `backend.app.services.conversation.artifacts` as the landing zone.
- Assumption: artifact tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_artifacts_phase0.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_artifacts_route.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_artifacts_404_real_cause.py` exist.

## Phase 3.5: Pre-Mortem

- Root and conversation extractors diverge further during migration.
- File conflict logic changes silently.
- The old root path is deleted before callers migrate.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/conversation/artifacts/`

Modules to create:
- `extractor.py`
- `artifact_rules.py`
- `content_variants.py`
- `conflict_policy.py`
- `versioning.py`
- `writers.py`

Implementation order:
1. Extract conflict and version helpers into pure modules.
2. Extract artifact-family handlers by artifact type.
3. Move write-side behavior into `writers.py`.
4. Move canonical `ArtifactExtractor` to `conversation/artifacts/extractor.py`.
5. Rewrite the root file as a compatibility shim importing from the canonical package.

Do-not-miss checklist:
- [ ] daily-planning extraction moved
- [ ] content-drafting extraction moved
- [ ] major-proposal extraction moved
- [ ] conflict/version helpers moved
- [ ] canonical path established
- [ ] old root import path preserved as shim

## Phase 5: Citation Audit

Re-verify before coding:
- `:27`
- `:39`
- `:123`
- `:316`
- `:515`
- `:1332`
- `:1413`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_artifacts_phase0.py \
  backend/tests/test_artifacts_route.py \
  backend/tests/test_artifacts_404_real_cause.py \
  backend/tests/test_task_execution_projection.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a shim import contract test for `backend.app.services.artifact_extractor`.
- Add per-artifact-family regression tests if extraction changes handler boundaries.
