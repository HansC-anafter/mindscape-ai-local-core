# Spatial Runtime Planning

This document explains the public planning/runtime story after `SpatialSchedulingIR` becomes a first-class planning artifact in Mindscape Local-Core.

It is intentionally written at the architecture level rather than the pack-internal level.

## Why This Document Exists

Mindscape no longer stops at "governed workflow planning."

For some jobs, the system also needs to govern:

- who or what is moving
- which anchors or objects matter
- what temporal segments should happen
- how the handoff remains traceable across runtime consumers

That is the role of `SpatialSchedulingIR`.

## The Planning Story In One Line

> **Meeting accepts governed intent → emits `TaskIR` and `SpatialSchedulingIR` → Local-Core stores only bounded summary/refs/trace → consumer runtimes execute and return bounded receipts**

## The Two Planes

### `TaskIR` = Control Plane

`TaskIR` remains responsible for:

- execution-ready work
- dependencies
- phase sequencing
- dispatch boundaries
- engine/runtime preference

It answers:

> what work should happen, in what order, under which execution boundary?

### `SpatialSchedulingIR` = Actuation Planning Plane

`SpatialSchedulingIR` is responsible for bounded spatial/world execution intent:

- entities such as actors, props, or cameras
- anchors or world references
- temporal segments
- consumer-neutral constraints
- stable schedule identity for downstream handoff

It answers:

> what spatial/world actuation intent is being planned, and how should downstream consumers interpret it without collapsing governance and execution into one artifact?

## What Local-Core Stores

Local-Core does not store provider-native runtime payloads as world memory.

It stores bounded summary surfaces such as:

- `schedule_id`
- artifact refs
- consumer receipt refs
- revision refs
- active window or active segment summary
- bounded schedule constraints

This keeps Local-Core as a governance and continuity host instead of turning it into a backend cache.

## Stable IDs Are The Handoff Spine

The handoff story is not:

- "copy this file path into the next pack"

The handoff story is:

- one meeting produces one bounded schedule identity
- downstream consumers refer back through stable IDs
- runtime receipts can be traced back to the originating schedule
- world summary and writeback can describe the same schedule without embedding raw runtime payloads

This is what lets the system behave like a governed world/runtime OS rather than a loose collection of adapters.

## The Two-Layer Acceptance Gate

### Layer 1: `schedule -> summary -> handoff -> stable IDs`

The first layer proves that the central planning spine is real.

Minimum proof:

- one meeting-originated demo
- one `TaskIR`
- one `SpatialSchedulingIR`
- one bounded world summary
- one downstream receipt or preview receipt
- one stable-ID mapping that shows schedule continuity end-to-end

Recommended public-safe hero demo:

- [Meeting-Originated Coffee Spatial Demo](../use-cases/meeting-originated-coffee-spatial-demo.md)
- [Counter-Camera Non-Actor Spatial Demo](../use-cases/counter-camera-nonactor-spatial-demo.md)

### Layer 2: Stronger Motion Backend Replaceability

The second layer proves that the system is not hard-bound to a single motion lane.

Minimum proof:

- the same schedule/handoff contract can drive a baseline lane and a stronger runtime consumer
- the stronger lane does not require changing the central IR schema
- stable IDs and bounded writeback remain intact

This second layer is not about pulling provider-specific APIs into Local-Core.

It is about proving that consumers are replaceable while governance stays stable.

## Current Public Milestone Status

The current reference-host milestone status is:

- **Layer 1 closed**: the public-safe coffee demo now has a real downstream receipt, bounded world summary continuity, stable-ID mapping, and an operator-facing capture.
- **Layer 2 closed**: the same schedule spine now reaches a live `motion_runtime -> ComfyUI/Kimodo` stronger lane, returns a completed stronger-backend receipt, and preserves stable IDs plus bounded writeback.
- **Milestone closed**: the reference host now demonstrates both acceptance layers on one stable schedule spine.
- **Non-actor scenario closed as well**: the counter-camera scenario now proves that `object / camera / zone` semantics can ride the same dual-artifact planning model, reach a real downstream `multi_media_studio` receipt, and close a stronger `motion_runtime` receipt without changing central IR schema.

## What This Planning Model Proves

- Mindscape can separate control-plane execution from spatial/world planning
- Local-Core can host bounded world/runtime continuity without swallowing raw runtime payloads
- downstream packs can remain pack-owned while sharing a stable handoff spine

## What This Planning Model Does Not Prove

- that every runtime consumer is already integrated
- that a stronger motion backend is already production-ready on every host
- that the public hero demo automatically implies polished final animation quality

## Related Documents

- [System Overview](./system-overview.md)
- [Governed Memory Fabric](./governed-memory-fabric.md)
- [Local/Cloud Boundary](./local-cloud-boundary.md)
- [Meeting-Originated Coffee Spatial Demo](../use-cases/meeting-originated-coffee-spatial-demo.md)
- [Counter-Camera Non-Actor Spatial Demo](../use-cases/counter-camera-nonactor-spatial-demo.md)
- [Demo Gallery](../demo-gallery/README.md)
