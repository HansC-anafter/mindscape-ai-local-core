# Use Case: `@ipu__pilates` Supporting Demo

> **Category**: Spatial Runtime / Single-Image Supporting Lane  
> **Complexity**: Medium  
> **Current status**: public-safe supporting demo with one checked-in closure candidate

## 1. Scenario Overview

This page exists to answer a narrower question than the hero demos:

> can a real, curated studio reference from `@ipu__pilates` be promoted into a public-safe supporting demo with checked-in image and mesh evidence?

The answer on the current branch is now:

- yes for one public-safe subset reference
- no, not yet for the entire six-reference curated lane

The first promoted supporting demo is:

- `DRjrJ5KkoS4`

## 2. What Goes In

The bounded input for this supporting lane is:

- one curated `@ipu__pilates` reference image
- one public-safe subset decision recorded in the curated-lane manifest
- one single-image bootstrap run that produces a reviewable scene/person closure candidate

This is not a meeting-originated spatial/world story.

It is a productization lane for turning a real reference family into a public-safe, inspectable artifact story.

## 3. What Comes Out

The current public-safe outputs are:

- one checked-in source image
- one checked-in preview render
- one public summary JSON
- one internal evidence bundle containing:
  - `scene_model.glb`
  - `scene_mesh.glb`
  - `person_model.glb`
  - `person_mesh.glb`
  - `workfile.blend`
  - `single_image_bootstrap_receipt.json`

The public docs intentionally stop at image evidence plus bounded status language.

The operator-grade bundle remains in internal evidence.

## 4. Why This Supporting Demo Matters

This page closes a truth gap that existed before:

- generic preview-mesh lanes were present
- `@ipu__pilates` had curated refs
- but there was no checked-in public-safe example that actually matched that studio reference family

Now there is one.

That means the repo can say something more precise:

- there is a generic single-image preview lane
- and there is now also one real curated-reference supporting demo from `@ipu__pilates`

## 5. Public Evidence

Current checked-in public-safe evidence:

![ipu__pilates source](../assets/demo-gallery/d6-ipu-pilates-supporting-demo-01-source.jpg)

![ipu__pilates preview render](../assets/demo-gallery/d6-ipu-pilates-supporting-demo-02-preview-render.png)

Summary:

- [`d6-ipu-pilates-supporting-demo-summary.json`](../assets/demo-gallery/d6-ipu-pilates-supporting-demo-summary.json)

## 6. What This Proves

- the `@ipu__pilates` lane is no longer only an internal staging lane
- at least one curated reference now has public-safe source-plus-preview evidence
- the repo can distinguish a real curated-reference supporting demo from the generic indoor clean-space lane
- the corresponding mesh/workfile closure exists in internal evidence

## 7. What This Does Not Prove

- that all six curated `@ipu__pilates` references are already productized
- that the current closure is a polished final geometry claim
- that the current runtime should be described as a formal `SAM3D` asset lane

Use honest status language:

> this is a public-safe supporting demo with a checked-in closure candidate, not the final public hero demo for the full `@ipu__pilates` reference family

## 8. Current Runtime Honesty Note

The current checked-in closure candidate uses the currently validated supporting runtime family:

- `runtime_family = triposr`
- `promotion_state = candidate`
- `primary_contract_ready = true`

That means:

- bounded artifact closure is real
- inspectable mesh/workfile evidence exists
- but this page must not market the result as a formal `SAM3D` production-grade asset

## 9. Related Docs

- [Demo Gallery](../demo-gallery/README.md)
- [Single-Image Preview Mesh](./single-image-preview-mesh.md)
- [Artifact Taxonomy](../reference/artifact-taxonomy.md)
- [Use Case Gallery](./README.md)
