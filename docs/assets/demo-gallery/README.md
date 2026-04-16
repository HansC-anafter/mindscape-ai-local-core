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

### D1. Single-Image Preview Mesh

- `01-source.png`: copyright-safe source image used for the smoke run
- `02-preview-render.png`: Blender Workbench capture from the generated review bundle
- `03-oblique-view.png`: documentation capture that shows the candidate bundle at an inspectable angle
- `04-side-view.png`: documentation capture that proves non-flat mesh depth
- `05-separation-proof-card.png`: public-safe operator-facing proof card for the scene/person split
- `06-artifact-ledger-card.png`: public-safe artifact inventory card derived from the bundle manifest
- `summary.json`: machine-readable smoke result with status, warnings, and artifact refs
- `views-summary.json`: camera and shot metadata for the documentation captures
- `doc-cards-summary.json`: trace file for the generated documentation cards

### D5. Candidate vs Fallback Comparison

- `01-fallback-preview-render.png`: degraded fallback preview render captured from the same source image family as D1
- `02-compare-card.png`: public-safe comparison card for the candidate and fallback lanes
- `fallback-execution-summary.json`: execution summary for the current degraded fallback evidence
- `compare-card-summary.json`: trace file for the generated comparison card

### D3. Complex Relation Stress Preview Mesh

- `01-source.jpeg`: copyright-safe denser indoor source image used for the stress or honesty lane
- `02-preview-render.png`: front-facing preview still from the generated Blender bundle
- `03-oblique-view.png`: documentation capture that makes the rough spatial split easier to inspect
- `04-side-view.png`: documentation capture that proves non-flat candidate depth under a messier scene
- `summary.json`: public-safe summary for current stress-lane status, warnings, and claims
- `views-summary.json`: shot metadata for the checked-in stills

## Public-safe Rules

- Keep titles and captions provider-neutral unless provider naming is needed for operator debugging.
- Mark preview geometry as `preview`, `candidate`, or `fallback` when applicable.
- Do not store pack-private implementation notes in this directory.
- Prefer synthetic or license-reviewed inputs for the first public-facing captures.

## Tooling Boundary

- demo-only generation helpers belong under `docs-internal/implementation/2026-04-16/tools/`
- do not add doc-capture helpers to repo-level `scripts/` unless they are being promoted into a supported workflow
