# Use Case: Candidate vs Fallback Comparison

> **Category**: Spatial Runtime / Honesty Layer  
> **Complexity**: Low  
> **Current status**: Supporting honesty lane; public deep dive published, compare asset re-landing pending on this branch

## 1. Scenario Overview

This page exists to answer one public-facing governance question:

> how does the repo talk honestly about a stronger path and a degraded path without pretending they are equivalent?

The value of this page is not visual polish.

The value is honesty:

- one stronger or candidate lane
- one degraded or fallback lane
- one clear explanation of when to use which

## 2. What Goes In

The comparison should use:

- one comparable source image or source scenario family
- one candidate path
- one fallback path
- one public-safe explanation of why the fallback exists

## 3. What Comes Out

The intended public-safe outputs are:

- a simple comparison summary
- clear status words
- one explanation of what the fallback protects against

## 4. What This Proves

- the repo does not hide degraded paths
- `candidate` and `fallback` are part of the governance story, not embarrassing exceptions
- readers can understand why one path is preferred without assuming the fallback is broken

## 5. What This Does Not Prove

- that the fallback lane is equal to the candidate lane
- that every source image has a perfectly documented comparison asset on this branch
- that one comparison page alone is enough to certify overall modeling quality

Use honest status language:

> This page is an honesty layer for public demos, not proof that the fallback lane matches the primary lane.

## 6. Current Public Evidence Status

The compare card and fallback evidence bundle are not yet re-landed on the current branch.

That is why this page stays careful:

- it publishes the vocabulary
- it publishes the comparison logic
- it does not claim checked-in compare assets that are not actually present here

## 7. How To Explain The Difference

Use language like:

- `candidate lane`: stronger primary path with richer or more reviewable output
- `fallback lane`: degraded but bounded path that still preserves an explainable result

Avoid language like:

- `fallback means failure`
- `candidate and fallback are basically the same`

## 8. Related Docs

- [Single-Image Preview Mesh](./single-image-preview-mesh.md)
- [Complex Relation Stress Preview Mesh](./complex-relation-stress-preview-mesh.md)
- [Artifact Taxonomy](../reference/artifact-taxonomy.md)
- [Demo Gallery](../demo-gallery/README.md)
