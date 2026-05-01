# IG Backfill Hard Gates 2026-04-25

## Freeze

- Repo code frozen for this gate run. No new repo code edits were made after the user requested hard gates.
- This run used the current candidate source snapshot plus a read-only `/tmp` evaluator.
- No live refs were mutated.
- No pack was deployed.

## Snapshot

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Total ref metadata files scanned: `147505`
- Completed refs with `analysis_job.status=COMPLETED` and `vision_description` present: `4889`
- Raw machine output:
  - `/tmp/ig_backfill_gate_eval_snapshot.json`
  - `/tmp/ig_backfill_gate_eval_snapshot.log`

## Gate Definition

Each cohort is evaluated in two modes:

1. `full_reparse`
   - Re-run the current candidate parser on every raw payload in the cohort.
   - Hard fail if any parse fails, any clean row becomes non-clean, or any clean row drifts.

2. `targeted_repair`
   - Leave baseline-clean rows untouched.
   - Reparse and conservative-merge only baseline non-clean rows.
   - Hard fail if any targeted row remains non-clean or any targeted parse fails.

## Gate Results

| Cohort | Size | Baseline Clean | Baseline Bad | Full Reparse Clean | Full Reparse Fail | Clean Drift Under Full Reparse | Clean Regression Under Full Reparse | Targeted Repair Clean | Targeted Residual Bad | Targeted Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| recent_500 | 500 | 202 | 298 | 498 | 0 | 193 | 0 | 500 | 0 | PASS |
| recent_2000 | 2000 | 1197 | 803 | 1997 | 1 | 1175 | 0 | 1997 | 3 | FAIL |
| all_completed | 4889 | 3418 | 1471 | 4875 | 10 | 3387 | 10 | 4886 | 3 | FAIL |

Legend:
- `Full Reparse Fail` = `parse_failed`
- `Clean Drift Under Full Reparse` = baseline-clean rows whose parsed payload differs from current stored payload
- `Clean Regression Under Full Reparse` = baseline-clean rows that no longer audit as clean or hit parse failure

## Baseline Counts

### recent_500

- `clean=202`
- `field_collapse=285`
- `token_pollution=4`
- `mixed=9`

### recent_2000

- `clean=1197`
- `field_collapse=777`
- `token_pollution=6`
- `mixed=20`

### all_completed

- `clean=3418`
- `field_collapse=1445`
- `token_pollution=6`
- `mixed=20`

## Hard Conclusions

1. The current candidate parser is **not future-safe** for wholesale use.
   - `full_reparse` fails all three cohorts.
   - The failure is not marginal:
     - `recent_500`: `193` baseline-clean rows drift
     - `recent_2000`: `1175` baseline-clean rows drift
     - `all_completed`: `3387` baseline-clean rows drift and `10` clean rows regress hard

2. The current conservative repair strategy is **partially safe**, but not yet globally safe.
   - `recent_500`: passes
   - `recent_2000`: fails with `3` residual bad rows
   - `all_completed`: fails with the same `3` residual bad rows

3. The global blocker set is small but real.
   - The targeted-repair path is blocked by exactly `3` residual refs in both the `2000` and `all_completed` cohorts.

## Residual Blockers

### 1. Parser exception / parse failure

- `ref_8cfdae66` `@zhu_leisan` `DT-FfMPiDnG`
- Failure:
  - `camera_tech.framing.symmetry`
  - input value: `"No."`
  - boolean coercion fails in validation

### 2. Legacy token pollution survives in training annotations

- `ref_92e25c89` `@clio1008` `CsBq2pcv6HD`
- Baseline:
  - `training_lane_hints=['[']`
  - `material_tokens=['[']`
- After targeted merge:
  - `training_lane_hints=['[']` still survives

### 3. Legacy token pollution survives in training annotations

- `ref_038dc904` `@iazeros` `DRMk_0qknTx`
- Baseline:
  - `training_lane_hints=['[']`
  - `materials_inline_literal_collapse`
- After targeted merge:
  - `training_lane_hints=['[']` still survives

## Clean-Row Parser Exceptions Seen Under Full Reparse

These are direct proof that the current candidate parser cannot be pushed into future/global use yet:

- `ref_4be6c1d5` `@yangtorto` `BdnBbDKAmda`
  - `camera_tech.framing.rule_of_thirds='false.'`
  - `camera_tech.framing.symmetry='false.'`
  - `camera_tech.framing.leading_lines='false.'`
- `ref_75b703b4` `@krs.portrait` `CzyIP98S1WH`
  - `camera_tech.framing.symmetry='No.'`
  - `camera_tech.framing.leading_lines='Window frame lines.'`
- `ref_1ae76611` `@ayano_fukuoji` `DWgIfDRCD_F`
  - `camera_tech.framing.rule_of_thirds='false.'`
  - `camera_tech.framing.symmetry='false.'`
  - `camera_tech.framing.leading_lines='false.'`

## Gate Status

- `recent_500`
  - `full_reparse_future_safe = FAIL`
  - `targeted_repair_safe = PASS`
- `recent_2000`
  - `full_reparse_future_safe = FAIL`
  - `targeted_repair_safe = FAIL`
- `all_completed`
  - `full_reparse_future_safe = FAIL`
  - `targeted_repair_safe = FAIL`

## Decision

Current candidate snapshot does **not** clear the three hard gates.

Do **not**:

- deploy this parser/backfill snapshot
- apply wholesale repair to live refs
- apply targeted repair beyond the already-proven `recent_500` subset

Only after the `3` residual blockers are removed and the same three cohorts are re-run to zero residual bad rows should any repo-code advancement or live repair be considered.
