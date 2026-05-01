# IG Backfill Full Reparse Prototype Status 2026-04-26 V5

## Scope

- Prototype only.
- No live ref data changed.
- No repo business code changed.
- No deploy performed.
- Completed cohort source: live DB/API truth snapshot at `/tmp/ig_completed_refs_api.json`
- Completed cohort size: `5138`
- Evaluator snapshot: `/tmp/ig_backfill_gate_eval_snapshot_db_truth_v11.json`

## Final hard metrics

### Recent 500

- baseline: `clean=200 / bad=300`
- full reparse: `clean=500 / field_collapse=0 / token_pollution=0 / mixed=0 / parse_failed=0`
- targeted repair: `clean=500 / residual_bad=0`
- parser exceptions: `0`
- clean-row regression under full reparse: `0`
- semantic loss under full reparse: `0`
- gate result:
  - `targeted_repair_safe = true`
  - `full_reparse_future_safe = true`

### Recent 2000

- baseline: `clean=1176 / bad=824`
- full reparse: `clean=2000 / field_collapse=0 / token_pollution=0 / mixed=0 / parse_failed=0`
- targeted repair: `clean=2000 / residual_bad=0`
- parser exceptions: `0`
- clean-row regression under full reparse: `0`
- semantic loss under full reparse: `0`
- gate result:
  - `targeted_repair_safe = true`
  - `full_reparse_future_safe = true`

### All completed 5138

- baseline: `clean=3639 / bad=1499`
- full reparse: `clean=5138 / field_collapse=0 / token_pollution=0 / mixed=0 / parse_failed=0`
- targeted repair: `clean=5138 / residual_bad=0`
- parser exceptions: `0`
- clean-row regression under full reparse: `0`
- semantic loss under full reparse: `0`
- gate result:
  - `targeted_repair_safe = true`
  - `full_reparse_future_safe = true`

## What Changed Between V4 And V5

Two issues were closed in the `/tmp` prototype evaluator:

1. Structured raw extractors now prefer actual dict/list literals over earlier prose headings for:
   - `framing`
   - `light_source`
   - `materials`

2. `_simulate_cohort(...)` now passes `raw_text` into `_semantic_loss_details(...)`.
   Before that fix, single-row direct checks were green but batch gate evaluation still reported stale semantic loss because the raw-aware ignore logic was not being used.

## Meaning

This is the first prototype state where both of these are true on the correct live truth cohort:

- `targeted repair` is safe across `500 -> 2000 -> 5138`
- `full reparse` is also safe across `500 -> 2000 -> 5138`

Under the current `/tmp` prototype:

- parser exceptions are `0`
- parse failures are `0`
- token pollution residual is `0`
- field-collapse residual is `0`
- mixed residual is `0`
- clean-row regression is `0`
- semantic loss is `0`

## Current Conclusion

The prototype gate is now green end-to-end on the correct live DB/API truth cohort.

Repo business code still remains untouched.

The next step, if approved, is to port only the validated prototype logic from `/tmp/ig_backfill_gate_eval.py` into repo source and then rerun the same `500 -> 2000 -> 5138` gates against repo code before any deploy or live repair.
