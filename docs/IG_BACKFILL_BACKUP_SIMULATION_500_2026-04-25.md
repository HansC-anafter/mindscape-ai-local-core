# IG Backfill Backup Simulation 500 2026-04-25

## Scope

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Population: same `500` refs from [IG_BACKFILL_AUDIT_500_2026-04-25.md](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs/IG_BACKFILL_AUDIT_500_2026-04-25.md)
- Execution mode:
  - back up all `500` live metadata files
  - rewrite only the backup copies using the patched source parser/backfill path
  - do not touch live files

## Artifacts

- Backup root:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/tmp/ig_backfill_backup_500_20260425_105926`
- Backup manifest:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/tmp/ig_backfill_backup_500_20260425_105926/manifest.json`
- Rewrite diff report:
  - `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/tmp/ig_backfill_backup_500_20260425_105926/rewrite_diff_report.json`
- Dry-run proof after patch:
  - `/tmp/ig_recent500_dry_run_after_patch_v3.json`

## Backup Simulation Summary

- `total` = `500`
- `changed` = `500`
- `vision_description_changed` = `490`
- `training_annotations_changed` = `398`
- `auto_tags_changed` = `50`
- `analysis_debug_changed` = `500`
- `analysis_job_changed` = `500`
- `analysis_provenance_changed` = `500`

## What This Means

- The patched parser/backfill path can reparse the same `500` raw payloads into a detector-clean result under source-only dry-run (`clean=500`).
- But a backup-copy rewrite still changes `vision_description` on `490/500` rows.
- More importantly, it changes content even for many rows that the baseline audit marked `clean`.

## Baseline-Status Breakdown For Substantive Changes

- `field_collapse`
  - rows = `272`
  - substantive rows changed = `272`
- `mixed`
  - rows = `18`
  - substantive rows changed = `18`
- `token_pollution`
  - rows = `6`
  - substantive rows changed = `6`
- `clean`
  - rows = `204`
  - substantive rows changed = `194`

## Interpretation

This means the rewrite path is **not yet safe for wholesale live apply**.

The parser fixes clearly address the broken cases:
- `DD4f8asSDf8` → clean under dry-run
- `DMw6bNJyfwN` → clean under dry-run

But the same rewrite also mutates many rows that were previously classified as clean. The clean-row mutations are not only timestamp or bookkeeping noise; many include `vision_description` / `training_annotations` deltas.

## Example Clean-Row Risk

Example: `DNkkwYRyTrn`

- Scene summary stays the same
- Object count stays the same
- But rewritten payload still changes parts of `vision_description`, including training-annotation subfields such as `stance` / `body_orientation`

That means the current rewrite logic is still too eager to normalize some already-acceptable rows.

## Decision

Do **not** apply this wholesale to live `500` refs yet.

The safe next step is:
1. split the population into:
   - definitely-bad rows (`field_collapse`, `mixed`, `token_pollution`)
   - baseline-clean rows
2. only stage rewrite/apply for the definitely-bad set first
3. keep baseline-clean rows behind a stricter diff gate or a no-op guard
