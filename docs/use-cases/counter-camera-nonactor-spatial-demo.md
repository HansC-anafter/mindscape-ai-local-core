# Use Case: Counter-Camera Non-Actor Spatial Demo

> **Category**: Spatial Runtime / Non-Actor Planning
> **Complexity**: Medium
> **Current status**: Layer 1 closed, Layer 2 closed

## 1. Scenario Overview

This use case exists to prove the part that the coffee demo does not cover by itself:

> Mindscape can govern a bounded spatial/world handoff even when the key semantics are not only actor motion, but also object placement, camera reframing, and zone transition.

The operator says the job in plain language:

> have the subject enter from the cafe entry, carry a serving tray to the counter, place it on the service counter, let the main camera reframe from a wide entry shot to an over-shoulder counter shot, then have the subject exit toward the window zone

The system should then make that request legible as:

- one `TaskIR`
- one `SpatialSchedulingIR`
- one bounded world summary
- one downstream preview/runtime receipt
- one stronger motion receipt
- one stable-ID spine that ties the whole path together

This is the second public-safe milestone demo for `SpatialSchedulingIR` because it proves the planning model is not actor-only.

## 2. What Goes In

The minimum input is still intentionally simple:

- one plain-language meeting request
- two primary world objects: subject and serving tray
- one camera entity: main camera only
- one entry zone, one counter anchor, one window zone
- bounded governance constraints

The point is not cinematic polish.

The point is that a non-expert operator can understand the spatial intent immediately while the system keeps it bounded and traceable.

## 3. Bounded World-Proof Handoff

The scenario can be handed downstream as one bounded execution plan without expanding into provider-native payloads.

### Space Paragraphs

- one bounded `world_id` for the same cafe interior from start to finish
- `entry paragraph`: subject enters through the cafe entry while carrying the serving tray
- `counter paragraph`: subject approaches the service counter and places the tray on the counter anchor
- `window paragraph`: subject exits toward the window zone after the tray placement is complete

These paragraphs are different active regions inside one world, not separate scenes or world swaps.

### Active Objects And Anchors

- primary object `subject_01`
- primary object `serving_tray_01`
- single camera entity `camera_main_01`
- entry anchor `entry_zone`
- placement anchor `service_counter_anchor`
- exit anchor `window_zone`

The bounded handoff treats the subject and tray as the two primary world objects.

The camera stays a single named execution entity that can reframe, but it does not introduce a second camera lane or a second world.

### Constraint Summary

- `single_camera=true`
- `single_world=true`
- `dual_primary_objects=true`
- `replayable_schedule=true`
- no additional actors, props, or cameras may enter the schedule
- no scene cuts, world swaps, teleport jumps, or off-screen state rewrites may be introduced
- tray state changes are bounded to `carried -> placed_on_counter`
- schedule segments must remain ordered, named, and stable under the same `schedule_id`

### Spatial Scheduling

- `enter_establish`: `subject_01` enters through `entry_zone` while `camera_main_01` holds the wide establish view
- `approach_counter`: `subject_01` and `serving_tray_01` move together from `entry_zone` toward `service_counter_anchor`
- `place_tray`: `serving_tray_01` transitions from carried state to placed state on `service_counter_anchor`
- `camera_reframe`: the same `camera_main_01` reframes from wide entry coverage to over-shoulder counter coverage
- `exit_window`: `subject_01` leaves toward `window_zone` while `serving_tray_01` remains on `service_counter_anchor`

### Excluded Scope

- no secondary camera activation or multi-camera edit grammar
- no new prop introduction, tray duplication, or prop substitution
- no second subject, crowd, staff, or interaction partner
- no environment change beyond the single cafe interior world
- no return-to-counter pickup after tray placement
- no unbounded physics improvisation or consumer-specific animation detail encoded into Local-Core memory

### Bounded Execution Verdict

This handoff remains valid as a downstream world-proof package because it preserves one camera identity, one world identity, two primary world objects, three stable anchors, and one replayable segment order.

It is therefore suitable to hand off as a bounded execution plan through `TaskIR` + `SpatialSchedulingIR` + bounded world summary + downstream receipt references.

## 4. What Comes Out

The intended output package is:

1. a `TaskIR` that preserves control-plane execution boundaries
2. a `SpatialSchedulingIR` that carries bounded non-actor spatial/world intent
3. a bounded world summary that describes the active schedule without embedding runtime-native payloads
4. a real downstream `multi_media_studio` receipt that refers back to the same stable schedule identity
5. a real stronger `motion_runtime` receipt on the same stable schedule identity

The schedule is understandable at the segment level, for example:

- `enter counter`
- `camera establish`
- `place tray`
- `camera reframe`
- `exit window`

## 5. Why This Demo Matters

This demo closes the missing half of the milestone story:

- the planning model is not only about an actor interacting with a prop
- object placement can remain bounded and traceable
- camera intent can stay in the same schedule spine
- zone/anchor transitions survive the host-side planning path
- the same schedule identity can still drive both a downstream preview lane and a stronger motion lane

In other words, it proves that `SpatialSchedulingIR` is behaving more like a governed world/runtime planning artifact and less like a thin wrapper around one actor demo.

## 6. Layer 1 Acceptance Gate

Layer 1 proves:

> `schedule -> summary -> handoff -> stable IDs`

The current evidence package includes:

- meeting input
- `TaskIR` excerpt
- `SpatialSchedulingIR` excerpt
- bounded world summary
- one operator handoff manifest
- one real downstream `multi_media_studio` receipt
- one stable-ID mapping table
- one operator-facing capture

### Stable-ID Mapping Table

At minimum, the evidence lets an operator answer:

- which meeting produced the schedule?
- what is the `schedule_id`?
- which artifact ref represents the schedule artifact?
- which downstream receipt consumed it?
- what bounded world summary now describes it?

Current Layer 1 state:

- `closed`

## 7. Layer 2 Acceptance Gate

Layer 2 proves:

> the consumer is replaceable rather than hard-bound to a single lane

The public requirement is not "use one specific backend."

The public requirement is:

- the same schedule/handoff contract can drive a baseline lane
- the same schedule/handoff contract can also drive a stronger motion backend
- Local-Core still stores only bounded summary and trace
- the stronger backend does not require changing the central IR schema

Current Layer 2 state:

- the same `schedule_id=ssched_countercam00` now reaches a completed stronger `motion_runtime -> ComfyUI/Kimodo` receipt
- `layer2-consumer-compare.json` confirms `same_schedule_identity=true`
- `central_ir_schema_changed=false`
- `bounded_writeback_preserved=true`

Current Layer 2 status:

- `closed`

## 8. Operator Flow

The operator journey is explainable as:

1. **World Assets** — the operator understands which subject, object, camera, and zones matter
2. **Meeting** — one plain-language request becomes `TaskIR` plus `SpatialSchedulingIR`
3. **Bridge Review** — the operator can inspect the bounded schedule summary and stable IDs
4. **Render / Preview** — a downstream `multi_media_studio` run accepts the same schedule identity
5. **Stronger Motion Lane** — a stronger `motion_runtime` lane completes on the same schedule identity
6. **Writeback** — the world summary remains bounded and traceable

The minimal operator package therefore names:

- `meeting_id`
- `task_id`
- `schedule_id`
- `schedule_artifact_ref`
- `world_summary_ref`
- downstream `consumer_receipt_ref`
- stronger `consumer_receipt_ref`

## 9. Public Evidence Snapshot

Current public-safe evidence checked in on `2026-04-19`:

![Counter-camera operator capture](../assets/demo-gallery/d2-counter-camera-spatial-demo-operator-capture.png)

What this capture is meant to prove:

- the operator can inspect the bounded handoff flow without reading pack internals
- the non-actor scenario is not only a JSON claim; it also has an operator-facing proof surface
- the same run family that produced the capture also attached a real downstream receipt and then closed the stronger motion lane

What this capture is not meant to prove:

- polished final animation quality
- that every renderer-side artifact landing edge is solved on every workspace or host

## 10. What This Proves

- Mindscape can govern non-actor spatial semantics such as object placement, camera reframing, and zone transition
- `TaskIR` and `SpatialSchedulingIR` remain clearly separated
- Local-Core acts as a governed planning and continuity host
- runtime consumers remain swappable while sharing one stable schedule spine

## 11. What This Does Not Prove

- polished final animation quality
- that every visual-acceptance artifact landing path is already perfect
- that every future object/camera/route/zone scenario is automatically closed

Use honest status language:

> this is a closed non-actor milestone scenario for bounded spatial/world planning continuity, not a claim that every runtime-side operational edge has disappeared

## 12. Honest Runtime Note

The current reference-host evidence is strong enough to close Layer 1 and Layer 2, but one operational warning remains:

- the downstream `multi_media_studio` run reports a workspace foreign-key warning while landing one visual-acceptance artifact

This warning does **not** break the acceptance gates because:

- the stable schedule identity still survives into the first pack-facing downstream lane
- the stronger lane still completes on the same schedule identity
- the bounded writeback and compare contract remain intact

## 13. Related Docs

- [Demo Gallery](../demo-gallery/README.md)
- [Meeting-Originated Coffee Spatial Demo](./meeting-originated-coffee-spatial-demo.md)
- [Spatial Runtime Planning](../core-architecture/spatial-runtime-planning.md)
- [Architecture Documentation](../core-architecture/README.md)
- [System Overview](../core-architecture/system-overview.md)
