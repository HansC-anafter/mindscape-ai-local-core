# Use Case: Fixed-Scene Subject Swap

> **Category**: Spatial Runtime / Continuity Preview
> **Complexity**: Medium
> **Current status**: Preview continuity lane

## 1. Scenario Overview

**Goal**: preserve one scene identity while changing the subject-specific layer, so operators can preview continuity without rebuilding the entire scene every time.

This use case is a strong complement to single-image preview mesh because it shows the repo is not only generating one-off previews. It is also preserving reusable scene structure.

## 2. What Goes In

- one reusable scene package or fixed-scene reference
- a new subject variation or replacement target
- bounded continuity rules for what must stay fixed and what is allowed to change

## 3. What Comes Out

- multiple previews that share the same scene identity
- subject-specific variations that can be compared side by side
- bounded artifacts and traceability refs for the fixed-scene lane

## 4. What This Proves

- scene identity can survive across multiple subject variations
- the repo can package continuity, not only individual outputs
- downstream operator review can compare changes without reinterpreting the whole scene

## 5. What This Does Not Prove

- final multi-character compositing quality
- unrestricted scene editing for every world/runtime lane
- that all downstream runtime targets are equally mature

## 6. Suggested Screenshot Sequence

1. original fixed-scene input
2. preview with subject A
3. preview with subject B
4. quick comparison view showing what remained fixed

## 7. Operator Journey

1. prepare or obtain one fixed scene package
2. run a first subject preview
3. swap the subject-specific layer
4. review the before/after continuity
5. preserve the same scene package for future iterations

## 8. Public-safe Language

Prefer:

- `fixed-scene subject swap`
- `reuse one scene package while swapping the subject preview`
- `scene identity is preserved`

Avoid:

- talking about internal pack topology as the first explanation
- implying that every subject swap result is already production-ready

## 9. Related Docs

- [Demo Gallery](../demo-gallery/README.md)
- [Artifact Taxonomy](../reference/artifact-taxonomy.md)
- [Spatial Runtime Planning](../core-architecture/spatial-runtime-planning.md)
