# Demo Gallery

This gallery is the fastest way to understand what Mindscape can demonstrate today without starting from pack internals.

## How To Read These Demos

Every demo should answer five questions:

1. What goes in?
2. What comes out?
3. What does this prove?
4. What does this not prove?
5. What is the current status?

## Current Demo Cards

### 1. Single-Image Preview Mesh

- **What goes in**: one copyright-safe input image with a clear subject and scene
- **What comes out**: separate scene/person preview meshes plus a reviewable Blender bundle
- **What this proves**: a single image can be turned into bounded, inspectable preview assets
- **What this does not prove**: final production-grade 3D reconstruction
- **Current status**: candidate preview lane
- **Deep dive**: [Single-Image Preview Mesh](../use-cases/single-image-preview-mesh.md)

Current smoke evidence checked in on `2026-04-16`:

![D1 source input](../assets/demo-gallery/d1-single-image-preview-mesh-01-source.png)

`Source input`: a copyright-safe synthetic scene used for the first public-safe smoke capture.

![D1 preview render](../assets/demo-gallery/d1-single-image-preview-mesh-02-preview-render.png)

`Preview render`: a Blender Workbench capture from the generated review bundle. Treat this as a candidate preview artifact, not final geometry quality.

- **Evidence summary**: [`d1-single-image-preview-mesh-summary.json`](../assets/demo-gallery/d1-single-image-preview-mesh-summary.json)
- **Observed result**: `promotion_state=candidate`
- **Observed result**: `mesh_validation.primary_contract_ready=true`
- **Observed warnings**: `checkpoint_unspecified`, `runtime_cuda_unavailable`, `triposr_effective_marching_cubes_backend:skimage`, `subject_evidence_bbox_defaulted`
- **Extended proof in deep dive**: oblique/side captures plus operator-proof and artifact-ledger cards are now checked in on the use-case page

### 2. Fixed-Scene Subject Swap

- **What goes in**: one reusable scene package plus a new subject variation
- **What comes out**: multiple previews that preserve scene identity while changing the subject layer
- **What this proves**: scene continuity can be preserved while subject-specific outputs change
- **What this does not prove**: full multi-character production compositing
- **Current status**: preview continuity lane
- **Deep dive**: [Fixed-Scene Subject Swap](../use-cases/fixed-scene-subject-swap.md)

### 3. Scene Package Preview

- **What goes in**: multi-view or structured scene capture inputs
- **What comes out**: a scene package that can be handed to downstream consumers
- **What this proves**: scene identity and structure can be packaged as reusable assets
- **What this does not prove**: every downstream runtime import lane is closed
- **Current status**: active productization track

### 4. Object Preview Asset

- **What goes in**: a simple object-centric capture
- **What comes out**: a reusable preview asset or mesh sidecar
- **What this proves**: object-scale assets can be normalized into governed outputs
- **What this does not prove**: final cleanup for every object class
- **Current status**: active productization track

### 5. Candidate vs Fallback Comparison

- **What goes in**: one demo lane with both modeled and degraded paths
- **What comes out**: an honest side-by-side comparison
- **What this proves**: the repo explicitly distinguishes primary and degraded paths
- **What this does not prove**: the fallback lane is equivalent to the primary lane
- **Current status**: required honesty layer for public demos
- **Deep dive**: [Candidate vs Fallback Comparison](../use-cases/candidate-vs-fallback-comparison.md)

Current baseline checked in on `2026-04-16`:

- same-source comparison between the D1 modeled candidate lane and a `heuristic_depth_fallback` degraded lane
- fallback evidence currently focuses on preview/rendered output plus execution summary, not full parity with the candidate lane
- a public-safe comparison card is now checked in for faster onboarding

### 6. Complex Relation Stress Case

- **What goes in**: one denser indoor image with a subject plus multiple scene objects and surfaces
- **What comes out**: a rough but inspectable scene-plus-person candidate bundle
- **What this proves**: the preview artifact contract can still close on a harder image, not just the clean hero lane
- **What this does not prove**: polished production geometry or clean launcher behavior on every host
- **Current status**: candidate stress-case preview lane
- **Deep dive**: [Complex Relation Stress Preview Mesh](../use-cases/complex-relation-stress-preview-mesh.md)

Current baseline checked in on `2026-04-16`:

- public-safe source input plus `front / oblique / side` stills are now checked in
- the lane proves bounded artifact closure under messier indoor conditions
- this case should be read as an honesty layer, not as the first hero screenshot

## Screenshot Rule

When screenshots are added, each demo should include:

- source input
- operator-facing intermediate proof
- output artifact view
- status/limitation caption

If a checked-in still came from a headless/background Blender render, say so explicitly. That kind of capture is valid demo evidence, but it is not proof that an interactive Blender session remains open reliably on every host.

The D1 smoke set now includes `source input`, `side/oblique depth proof`, `operator-facing separation proof`, and `artifact ledger proof`. A literal Blender outliner screenshot remains optional if a more UI-oriented capture is desired.
