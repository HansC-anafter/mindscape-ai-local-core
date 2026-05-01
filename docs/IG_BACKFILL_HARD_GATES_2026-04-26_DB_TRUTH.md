# IG Backfill Hard Gates 2026-04-26 (DB/API Truth)

## Scope

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Cohort source: live `ReferenceIndex.query_page(... analysis_status=COMPLETED ...)`
- Snapshot file: `/tmp/ig_completed_refs_api.json`
- Evaluator: `/tmp/ig_backfill_gate_eval.py`
- Generated at: `2026-04-26 Asia/Taipei`

## Important Correction

The previous hard-gate run that used `4889/4925` completed rows is invalid for workbench truth.

That earlier run mixed file-scan / metadata completed rows with workbench counts.

This report uses the live DB/API completed cohort instead:

- `completed_api_total = 5138`

## Cohort Integrity Notes

- A host-side offset-paginated API snapshot only fetched `4936/5138` rows because the sorted result set moved while analysis was still running.
- The final cohort used here was rebuilt from backend-container `ReferenceIndex.query_page(...)`, which returned the full `5138` rows.

## Gate Result Summary

### `recent_500`

- Cohort size: `500`
- Baseline:
  - `clean = 200`
  - `field_collapse = 286`
  - `token_pollution = 5`
  - `mixed = 9`
- Full reparse:
  - `clean = 498`
  - `field_collapse = 2`
  - `parse_failed = 0`
  - `clean_row_drift_under_full_reparse = 195`
  - `clean_row_regression_under_full_reparse = 0`
- Targeted repair:
  - `clean = 500`
  - `targeted_residual_bad = 0`
  - `parse_failed = 0`
- Verdict:
  - `full_reparse_future_safe = false`
  - `targeted_repair_safe = true`

### `recent_2000`

- Cohort size: `2000`
- Baseline:
  - `clean = 1176`
  - `field_collapse = 797`
  - `token_pollution = 7`
  - `mixed = 20`
- Full reparse:
  - `clean = 1998`
  - `field_collapse = 2`
  - `parse_failed = 0`
  - `clean_row_drift_under_full_reparse = 1152`
  - `clean_row_regression_under_full_reparse = 0`
- Targeted repair:
  - `clean = 2000`
  - `targeted_residual_bad = 0`
  - `parse_failed = 0`
- Verdict:
  - `full_reparse_future_safe = false`
  - `targeted_repair_safe = true`

### `all_completed`

- Cohort size: `5138`
- Baseline:
  - `clean = 3639`
  - `field_collapse = 1472`
  - `token_pollution = 7`
  - `mixed = 20`
- Full reparse:
  - `clean = 5125`
  - `field_collapse = 4`
  - `parse_failed = 9`
  - `clean_row_drift_under_full_reparse = 3606`
  - `clean_row_regression_under_full_reparse = 10`
  - `parser_exception_count = 2`
- Targeted repair:
  - `clean = 5129`
  - `targeted_residual_bad = 0`
  - `parse_failed = 0`
- Verdict:
  - `full_reparse_future_safe = false`
  - `targeted_repair_safe = true`

## Hard Conclusion

The current candidate is **not safe** for full future reparse.

It is only safe in the narrower targeted-repair mode evaluated here.

That means:

- Do **not** promote the current full-reparse logic into the main analysis path.
- Do **not** wholesale rewrite all completed rows.
- The currently tested targeted-repair path clears all detected bad rows across:
  - `recent_500`
  - `recent_2000`
  - `all_completed = 5138`

## Clean-Row Regression Evidence Under Full Reparse

Full reparse still causes unacceptable drift on rows that were baseline-clean.

Counts:

- `recent_500`: `195`
- `recent_2000`: `1152`
- `all_completed`: `3606`

Regressions to materially worse output:

- `all_completed`: `10`

## Parser Exceptions Still Seen Under Full Reparse

### `ref_75b703b4` / `CzyIP98S1WH` / `@krs.portrait`

- Failure:
  - `camera_tech.framing.leading_lines = 'Window frame lines.'`
- Why it matters:
  - Boolean framing field still accepts prose drift in some raws.

### `ref_1ae76611` / `DWgIfDRCD_F` / `@ayano_fukuoji`

- Failure:
  - `camera_tech.framing.rule_of_thirds = 'false.'`
  - `camera_tech.framing.symmetry = 'false.'`
- Why it matters:
  - Boolean normalization still misses punctuated boolean prose.

## Files

- Snapshot:
  - `/tmp/ig_completed_refs_api.json`
- Raw evaluator output:
  - `/tmp/ig_backfill_gate_eval_snapshot_db_truth.json`
- This report:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs/IG_BACKFILL_HARD_GATES_2026-04-26_DB_TRUTH.md`
