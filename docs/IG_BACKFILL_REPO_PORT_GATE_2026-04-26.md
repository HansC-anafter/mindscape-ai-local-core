# IG Backfill Repo Port Gate 2026-04-26

## Scope

- Target repo parser: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/models/vision_output_parser.py`
- Completed cohort source: `/tmp/ig_completed_refs_api.json`
- Completed cohort size used for final gate: `5138`
- This round did **not** deploy, did **not** mutate live refs, and did **not** run any live repair.

## Final Gate Results

### recent_500

- Status: passed
- Full reparse future safe: `true`

### recent_2000

- Status: passed
- Full reparse future safe: `true`
- Snapshot: `/tmp/recent2000_direct_repo_gate_current.json`

### all_completed

- Status: passed
- Full reparse future safe: `true`
- Snapshot: `/tmp/all_completed_direct_repo_gate_current.json`

## Final all_completed Metrics

- `cohort_size=5138`
- `baseline_bad_count=1499`
- `reparse_counts.clean=5138`
- `reparse_counts.field_collapse=0`
- `reparse_counts.token_pollution=0`
- `reparse_counts.mixed=0`
- `reparse_counts.parse_failed=0`
- `clean_row_regression_under_full_reparse=0`
- `semantic_loss_under_full_reparse=0`
- `parser_exception_count=0`
- `targeted_residual_bad=0`

## Repo Parser Changes Landed

- Preserve and normalize `training_annotations` before raw fill-back so stance/body-orientation salvage is not dropped.
- Expand `training_annotations.stance` salvage for non-human and non-standard pose labels such as `perched`, `coiled`, `jumping`, `dynamic`, `various`, `swimming`, `floating`.
- Normalize malformed or polluted `material.materials` rows instead of only filling when blank.
- Extract best `materials` candidate from raw by scanning repeated `materials:` occurrences and preferring usable structured candidates over placeholder `[] (...)` scaffolds.
- Recover `subjects` and `objects` from later structured raw candidates when early candidates are empty or malformed.
- Harden subject corruption checks so malformed placeholder objects with non-dict nested fields are dropped instead of crashing normalization.
- Coerce descriptive framing booleans enough to avoid parser exceptions during full reparse.

## Notes

- Structured prose salvage warnings still appear during evaluation for some raws, but they no longer produce:
  - parser exceptions
  - parse_failed rows
  - token pollution
  - field collapse
  - semantic loss

- The repo parser is now aligned with the previously validated `/tmp` prototype at the gate level.
