# Use Case: Fixed-Scene Subject Swap

> **Category**: Spatial Runtime / Continuity Preview  
> **Complexity**: Medium  
> **Current status**: Supporting preview continuity lane; public deep dive published, screenshot bundle pending

## 1. Scenario Overview

This use case exists to make one continuity claim easy to understand:

> the system can preserve scene identity while changing the subject-specific layer.

This is not the same as final multi-character compositing.

It is a continuity story:

- keep the scene package or scene identity stable
- change the subject layer
- inspect whether the output remains legible as the same place

## 2. What Goes In

The minimum public-safe setup is:

- one reusable fixed scene
- one subject A preview or baseline
- one subject B preview or variant
- one bounded instruction that keeps the scene identity fixed

## 3. What Comes Out

The intended outputs are:

- multiple previews that share one scene identity
- subject-specific outputs that clearly differ
- a continuity story that can be explained without exposing pack internals

## 4. What This Proves

- scene continuity can be reused rather than recreated every time
- a bounded continuity lane can be described in operator-facing language
- the public docs can separate `scene identity` from `subject variation`

## 5. What This Does Not Prove

- final production compositing quality
- that every scene-swap lane is already fully automated on every host
- that multiple subject variants are interchangeable with no downstream review

Use honest status language:

> This is a continuity preview lane that proves reusable scene identity, not final production compositing.

## 6. Current Public Evidence Status

This page is published as a public reference lane even though the screenshot bundle is still pending on the current branch.

That is acceptable because:

- the scenario family is real and already part of the public reading journey
- the page makes the continuity semantics legible
- the status language is explicit about what is and is not yet landed

## 7. Operator Story

The operator should be able to explain this lane in one sentence:

> keep the room, table, or scene package recognizable, but swap the subject-specific preview layer.

If the explanation requires pack names or implementation-specific payloads, the page has failed its job.

## 8. Related Docs

- [Demo Gallery](../demo-gallery/README.md)
- [Meeting-Originated Coffee Spatial Demo](./meeting-originated-coffee-spatial-demo.md)
- [Counter-Camera Non-Actor Spatial Demo](./counter-camera-nonactor-spatial-demo.md)
- [Artifact Taxonomy](../reference/artifact-taxonomy.md)
