# IG Backfill Full-Reparse Prototype Status 2026-04-26

## Scope

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Completed cohort source: live backend `ReferenceIndex.query_page(... analysis_status=COMPLETED ...)`
- Completed cohort size: `5138`
- Prototype only: `/tmp/ig_backfill_gate_eval.py`
- No repo business code changed
- No deploy
- No live ref data changed

## What Was Fixed In The Prototype

Three concrete blocker classes were removed in the `/tmp` prototype:

1. `no raw => no-op`
- Historical completed rows with empty `analysis_debug.raw_text` no longer count as full-reparse parse failures.
- They are treated as preserve-existing rows.

2. framing bool normalization
- `rule_of_thirds / symmetry / leading_lines` now normalize both:
  - JSON-ish keys such as `rule_of_thirds: false.`
  - markdown/prose headings such as `Leading Lines: Window frame lines.`

3. fake clothing item cleanup
- Subject clothing items like:
  - `garment_type = "garment"`
  - `color = "None"`
- are dropped before reparsed payload audit.

## Current Prototype Result

### `recent_500`
- Full reparse:
  - `clean = 500`
  - `parse_failed = 0`
  - `clean_row_regression = 0`
- Targeted repair:
  - `clean = 500`

### `recent_2000`
- Full reparse:
  - `clean = 2000`
  - `parse_failed = 0`
  - `clean_row_regression = 0`
- Targeted repair:
  - `clean = 2000`

### `all_completed = 5138`
- Full reparse:
  - `clean = 5138`
  - `field_collapse = 0`
  - `token_pollution = 0`
  - `mixed = 0`
  - `parse_failed = 0`
  - `parser_exception_count = 0`
  - `clean_row_regression_under_full_reparse = 0`
- Targeted repair:
  - `clean = 5138`

## Remaining Gap

The old hard gate still reports:

- `clean_row_drift_under_full_reparse = 3608`

That number is now **drift**, not breakage.

It is dominated by non-regression differences such as:

- `_thinking`
- punctuation normalization in `evidence_notes`
- richer `objects / material / style / raw_description`
- `uncertainty: 0.0 -> null`
- legacy sparse rows becoming more explicit but still valid

So the prototype is now at:

- `functional regressions = 0`
- `parser exceptions = 0`
- `parse failures = 0`
- `audit regressions = 0`

The only remaining blocker to calling full reparse "safe" is the old bytewise drift gate.

## Files

- Snapshot:
  - `/tmp/ig_backfill_gate_eval_snapshot_db_truth_v2.json`
- Raw log:
  - `/tmp/ig_backfill_gate_eval_snapshot_db_truth_v2.log`
- This report:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs/IG_BACKFILL_FULL_REPARSE_PROTO_STATUS_2026-04-26.md`
