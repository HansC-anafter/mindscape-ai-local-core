# IG Backfill Source Dry-Run 500 2026-04-25

## Scope

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Population: same `500` completed refs audited in [IG_BACKFILL_AUDIT_500_2026-04-25.md](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs/IG_BACKFILL_AUDIT_500_2026-04-25.md)
- Execution mode: source-only reparsing of live `analysis_debug.raw_text`
- Live safety: no metadata writes, no repair apply, no deploy-pack, no install
- Artifacts:
  - baseline audit: `/tmp/ig_recent500_audit.json`
  - dry-run after patch v3: `/tmp/ig_recent500_dry_run_after_patch_v3.json`

## Baseline

- `sample_size` = `500`
- `clean_count` = `204`
- `field_collapse_count` = `272`
- `token_pollution_count` = `6`
- `mixed_count` = `18`
- `read_errors` = `0`

## Dry-Run Result

- `sample_size` = `500`
- `clean_count` = `500`
- `field_collapse_count` = `0`
- `token_pollution_count` = `0`
- `mixed_count` = `0`
- `parse_failed_count` = `0`

## Parser Changes Exercised In Dry-Run

1. Hardened salvage stop-lines so prose salvage stops before:
   - `Let's construct/assemble/build the JSON`
   - `Output ONLY ... JSON`
   - `Return ONLY ... JSON`
   - top-level scaffold starts like `{`, `[`, and fenced ```json
2. Added nested subject mapping extraction for:
   - `coverage`
   - `pose`
   - `clothing`
   - `estimated_age_range`
3. Added inline literal handling for `material.materials`, including:
   - dict/list literal prefixes
   - nested dict bullets under `materials:`
   - simple `Thing: material` bullets with correct direction (`material_type=value`, `region=thing`)
4. Promoted leaked `camera_tech` / `environment` key-value items out of `evidence_notes` into their actual fields.

## Spot Checks

- `DD4f8asSDf8` → dry-run status `clean`
- `DMw6bNJyfwN` → dry-run status `clean`

## Important Boundaries

- This report proves the patched source parser/backfill path can reparse the same 500 raw payloads cleanly under dry-run.
- This report does **not** mean live refs were rewritten.
- The remaining unresolved issue family during dry-run was not backfill corruption; it was schema validation noise from upstream outputs that temporarily produced list-valued `facial_features` / `coverage_notes`, but `analyze_vision_output(...)` still returned a usable final result for all `500` rows.
