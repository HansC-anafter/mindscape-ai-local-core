# Use Case: Meeting-Originated Coffee Spatial Demo

> **Category**: Spatial Runtime / Milestone Acceptance
> **Complexity**: Medium
> **Current status**: Layer 1 closed, Layer 2 closed

## 1. Scenario Overview

This use case exists to prove a very specific product claim:

> Mindscape can now govern a dynamic spatial/world handoff, not just static artifact packaging.

The operator says the job in plain language:

> have the subject walk to the table, pick up the coffee cup, take a sip, then place it back

The system should then make that request legible as:

- one `TaskIR`
- one `SpatialSchedulingIR`
- one bounded world summary
- one downstream preview or runtime receipt
- one stable-ID spine that ties the whole path together

This is the first public-safe hero demo for the `SpatialSchedulingIR` milestone because it is understandable without knowing pack internals.

## 2. What Goes In

The minimum input is intentionally simple:

- one plain-language meeting request
- one subject
- one prop: coffee cup
- one anchor or table reference
- bounded governance constraints

The point is not cinematic complexity.

The point is that a non-expert operator can understand the intent immediately.

## 3. What Comes Out

The intended output package is:

1. a `TaskIR` that preserves control-plane execution boundaries
2. a `SpatialSchedulingIR` that carries bounded spatial/world intent
3. a bounded world summary that describes the active schedule without embedding runtime-native payloads
4. a downstream preview or runtime receipt that refers back to the same stable schedule identity

The schedule should be understandable at the segment level, for example:

- `approach`
- `grasp`
- `sip`
- `place`

## 4. Why This Demo Matters

This demo is the milestone acceptance lane because it closes several public claims at once:

- meeting emits dual artifacts instead of one overloaded IR
- Local-Core stores summaries, refs, and trace rather than provider-native payloads
- cross-pack handoff can be explained through stable IDs instead of manual file-path copying
- a dynamic world/runtime story can be shown without requiring readers to understand pack internals

## 5. Layer 1 Acceptance Gate

Layer 1 proves:

> `schedule -> summary -> handoff -> stable IDs`

The minimum evidence package should include:

- meeting input
- `TaskIR` excerpt
- `SpatialSchedulingIR` excerpt
- bounded world summary or world-card view
- one operator handoff manifest that spells out `World Assets -> Bridge Review -> Render`
- downstream preview or runtime receipt
- one stable-ID mapping table

### Stable-ID Mapping Table

At minimum, the evidence should let an operator answer:

- which meeting produced the schedule?
- what is the `schedule_id`?
- which artifact ref represents the schedule artifact?
- which consumer receipt or preview receipt consumed it?
- what bounded world summary now describes it?

## 6. Layer 2 Acceptance Gate

Layer 2 proves:

> the consumer is replaceable rather than hard-bound to a single lane

The public requirement is not "use one specific backend."

The public requirement is:

- the same schedule/handoff contract can drive a baseline consumer
- the same schedule/handoff contract can also drive a stronger motion backend
- Local-Core still stores only bounded summary and trace
- the stronger backend does not require central IR schema changes

If a stronger motion workflow such as an NVIDIA-backed lane is available, it is valuable here because it proves the handoff spine is platform-like rather than adapter-like.

Current honest status:

- Layer 1 is closed with a real downstream `multi_media_studio` receipt
- Layer 2 now reaches a live `motion_runtime -> ComfyUI/Kimodo` receipt on the current host
- the stronger lane preserves the same `schedule_id` and does not require central IR schema changes
- bounded writeback remains preserved
- the stronger lane now returns a completed stronger-backend receipt on the same schedule spine

## 7. Operator Flow

The milestone operator journey should be explainable as:

1. **World Assets** — the operator understands which subject, prop, and anchor matter
2. **Meeting** — one plain-language request becomes `TaskIR` plus `SpatialSchedulingIR`
3. **Bridge Review** — the operator can inspect the bounded schedule summary and stable IDs
4. **Render / Preview** — a downstream consumer returns a preview or runtime receipt
5. **Writeback** — the world summary remains bounded and traceable

If this flow requires tribal knowledge or manual path-copying, the milestone is not actually closed.

The minimal operator package should therefore include one bounded handoff manifest that names:

- `meeting_id`
- `task_id`
- `schedule_id`
- `schedule_artifact_ref`
- `world_summary_ref`
- `consumer_receipt_ref`

## 8. Public Evidence Snapshot

Current public-safe evidence checked in on `2026-04-18`:

![Coffee operator capture](../assets/demo-gallery/d0-coffee-spatial-demo-operator-capture.png)

What this capture is meant to prove:

- the operator can inspect the bounded handoff flow without reading pack internals
- the coffee run is not only a JSON claim; it also has an operator-facing proof surface
- the same run that produced the capture is the one that closed Layer 1 through a real downstream receipt

What this capture is not meant to prove:

- polished final animation quality
- that the stronger motion backend is already live-ready on this host

## 9. What This Proves

- Mindscape can present a public-safe dynamic spatial/world story
- `TaskIR` and `SpatialSchedulingIR` are clearly separated
- Local-Core acts as a governed planning and continuity host
- runtime consumers can remain pack-owned while sharing one traceable handoff spine

## 10. What This Does Not Prove

- polished final animation quality
- production readiness for every stronger motion backend on every host
- that every future object/camera/route/zone lane is already closed

Use honest status language:

> this is the milestone acceptance demo for bounded spatial/world planning continuity, not a claim that every runtime lane is already production-perfect

## 11. Related Docs

- [Demo Gallery](../demo-gallery/README.md)
- [Spatial Runtime Planning](../core-architecture/spatial-runtime-planning.md)
- [Architecture Documentation](../core-architecture/README.md)
- [System Overview](../core-architecture/system-overview.md)
