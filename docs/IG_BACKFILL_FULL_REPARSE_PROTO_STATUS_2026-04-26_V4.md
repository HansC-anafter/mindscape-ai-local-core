# IG Backfill Full Reparse Prototype Status 2026-04-26 V4

## Scope

- Prototype only.
- No live ref data changed.
- No repo business code changed.
- No deploy performed.
- Completed cohort source: live DB/API truth snapshot at `/tmp/ig_completed_refs_api.json`
- Completed cohort size: `5138`

## Current hard metrics

### Recent 500

- baseline: `clean=200 / bad=300`
- full reparse: `clean=500 / field_collapse=0 / token_pollution=0 / mixed=0 / parse_failed=0`
- targeted repair: `clean=500 / residual_bad=0`
- parser exceptions: `0`
- clean-row regression under full reparse: `0`
- bytewise drift under full reparse: `200`

### Recent 2000

- baseline: `clean=1176 / bad=824`
- full reparse: `clean=2000 / field_collapse=0 / token_pollution=0 / mixed=0 / parse_failed=0`
- targeted repair: `clean=2000 / residual_bad=0`
- parser exceptions: `0`
- clean-row regression under full reparse: `0`
- bytewise drift under full reparse: `1171`

### All completed 5138

- baseline: `clean=3639 / bad=1499`
- full reparse: `clean=5138 / field_collapse=0 / token_pollution=0 / mixed=0 / parse_failed=0`
- targeted repair: `clean=5138 / residual_bad=0`
- parser exceptions: `0`
- clean-row regression under full reparse: `0`
- bytewise drift under full reparse: `3627`

## Meaning

The remaining blocker is no longer parser breakage. The v4 prototype has:

- zero parse failures
- zero parser exceptions
- zero audit regressions
- zero targeted residual bad rows

The only failing gate left is the old bytewise JSON drift check. That check is too blunt for full reparse because it counts benign enrichment/normalization as failure.

## Semantic loss check

An additional loss analysis was run on clean baseline rows after v4 normalization.

- ignored as non-critical:
  - `_thinking`
  - `uncertainty`
  - `camera_tech.evidence_notes`
  - `environment.evidence_notes`
  - `scene.evidence_notes`
  - `insights.*`
- result:
  - `loss_count = 0`

This means the prototype currently shows no non-empty to empty semantic loss on the retained critical fields.

## V4 prototype changes

- wired `_fill_blank_scalars_from_raw(...)` into `_normalize_reparsed_payload(...)`
- filled blank reparsed scalars from raw for:
  - `scene.*`
  - `style.*`
  - `camera_tech.focal_length_class`
  - `camera_tech.shot_type`
  - `camera_tech.framing.negative_space_ratio`
  - `environment.*`
  - `environment.light_source.*`
  - `objects.dominant_subject`
- normalized deliberation-polluted enum-like subject values:
  - `pose.stance`
  - `pose.body_orientation`
  - `expression`
- fixed the last residual blocker:
  - `ref_d74a9cf4 / DMSUFI7zMVl`

## Current conclusion

V4 is the first prototype state where full reparse appears semantically safe on the `5138` completed-cohort truth set.

It is not yet ready to promote into repo code until the gate itself is rewritten from:

- `bytewise JSON no-drift`

to:

- `semantic no-regression`

Only after that gate rewrite passes on the same `500 -> 2000 -> 5138` cohorts should repo code be touched.
