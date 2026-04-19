# Demo Gallery Assets

This directory stores public-safe demo assets that back the docs pages in `docs/demo-gallery` and `docs/use-cases`.

## Naming Contract

Use the pattern:

- `d<number>-<demo-slug>-<sequence>-<asset-kind>.<ext>`

Examples:

- `d1-single-image-preview-mesh-01-source.png`
- `d1-single-image-preview-mesh-02-preview-render.png`
- `d1-single-image-preview-mesh-summary.json`

## Current Asset Set

### D0. Meeting-Originated Coffee Spatial Demo

- `d0-coffee-spatial-demo-operator-capture.png`: operator-facing capture from the closed Layer 1/Layer 2 milestone run

### D2. Counter-Camera Non-Actor Spatial Demo

- `d2-counter-camera-spatial-demo-operator-capture.png`: operator-facing capture from the closed non-actor milestone run

### D1. Single-Image Preview Mesh

- `d1-indoor-clean-space-01-source.png`: public-safe indoor clean-space source image used for the supporting preview lane
- `d1-indoor-clean-space-02-preview-render.png`: Blender preview render from the checked-in supporting lane
- `d1-indoor-clean-space-03-oblique-view.png`: documentation still for inspectable angled review
- `d1-indoor-clean-space-04-side-view.png`: documentation still showing non-flat preview depth
- `d1-indoor-clean-space-summary.json`: smoke/result summary for the supporting lane
- `d1-indoor-clean-space-views-summary.json`: shot metadata for the checked-in stills

This checked-in D1 set is a generic public-safe indoor preview lane.
It is not the `@ipu__pilates` studio reference set.

### D3. Complex Relation Stress Preview Mesh

- `01-source.jpeg`: copyright-safe denser indoor source image used for the stress or honesty lane
- `02-preview-render.png`: front-facing preview still from the generated Blender bundle
- `03-oblique-view.png`: documentation capture that makes the rough spatial split easier to inspect
- `04-side-view.png`: documentation capture that proves non-flat candidate depth under a messier scene
- `summary.json`: public-safe summary for current stress-lane status, warnings, and claims
- `views-summary.json`: shot metadata for the checked-in stills

### D6. `@ipu__pilates` Supporting Demo

- `d6-ipu-pilates-supporting-demo-01-source.jpg`: the first public-safe curated source still promoted from the dedicated `@ipu__pilates` lane
- `d6-ipu-pilates-supporting-demo-02-preview-render.png`: preview render captured from the corresponding Stage C closure bundle
- `d6-ipu-pilates-supporting-demo-summary.json`: bounded public summary for the checked-in supporting demo

This D6 set is not the full `@ipu__pilates` curated lane.
It is the first public-safe checked-in supporting closure candidate from that lane.

## Documented But Not Yet Re-Landed On This Branch

These lanes already have published public docs and status language, but their earlier public-safe screenshot/card sets are not currently present in this directory:

### D4. Fixed-Scene Subject Swap

- supporting continuity lane
- public deep dive is published, but screenshot bundle is still pending

### D5. Candidate vs Fallback Comparison

- supporting honesty layer
- compare card and fallback evidence need re-landing before this directory can claim checked-in public assets for D5

## Public-safe Rules

- Keep titles and captions provider-neutral unless provider naming is needed for operator debugging.
- Mark preview geometry as `preview`, `candidate`, or `fallback` when applicable.
- Do not store pack-private implementation notes in this directory.
- Prefer synthetic or license-reviewed inputs for the first public-facing captures.

## Tooling Boundary

- demo-only generation helpers belong under `docs-internal/implementation/2026-04-16/tools/`
- do not add doc-capture helpers to repo-level `scripts/` unless they are being promoted into a supported workflow
