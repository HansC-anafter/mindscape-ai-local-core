# Spatial Runtime Planning

This document explains the public architecture split between `TaskIR` and `SpatialSchedulingIR`.

## Why This Split Exists

Mindscape needs two different artifact layers:

1. a **control-plane artifact** that says what should execute next
2. a **planning-plane artifact** that says how a spatial/world-aware workflow is structured

Trying to force both jobs into one artifact leads to two failures:

- governance and provider/runtime payloads become mixed together
- the first working consumer lane becomes the accidental owner of the entire abstraction

## Public Framing

Use this model:

> **Meeting Runtime → TaskIR / SpatialSchedulingIR → Consumer Runtimes → Runtime Receipts → World Summary / Writeback**

## What `TaskIR` Does

`TaskIR` is the bounded control-plane artifact.

It carries:

- execution-ready work
- dependencies
- dispatch boundaries
- artifact references
- engine/runtime preferences

It does **not** try to encode every provider-native runtime request.

## What `SpatialSchedulingIR` Does

`SpatialSchedulingIR` is the bounded planning-plane artifact for spatial/world execution intent.

It carries:

- entities such as subject/object/camera/zone
- time windows or segments
- anchors and placement hints
- constraint summaries
- consumer hints
- artifact references and traceability keys

It does **not** try to become:

- a provider-native runtime payload
- a universal physics engine
- the raw per-frame data store

## Why The Planning Plane Matters

Without a separate planning plane, the system tends to collapse into one of two bad states:

1. `TaskIR` becomes overloaded with spatial/runtime payload detail
2. the first consumer pack becomes the de facto owner of the planning abstraction

The separate planning plane keeps local-core in the right role:

- local-core owns governed planning and traceable artifact emission
- consumer/runtime packs own provider-specific execution

## Relationship To Governed Memory

The governed memory layer should ingest:

- schedule summaries
- constraint summaries
- runtime receipts
- artifact references
- traceability keys such as `source_schedule_id`

It should **not** ingest:

- raw provider-native execution payloads
- raw per-frame curves
- opaque backend caches dumped as memory

## Relationship To Project / Flow / Playbook

`Project / Flow / Playbook` remains an important consumer path.

It is no longer the only public mental model for the repo.

Other consumer paths can include:

- preview mesh/runtime lanes
- scene package/runtime lanes
- motion/runtime lanes
- external runtime consumers that respect the bounded artifact contracts

## P0 Public Promises

For the current public story, P0 means:

- `TaskIR` and `SpatialSchedulingIR` are different artifacts with different jobs
- consumer packs can share one planning artifact
- writeback remains summary-first and bounded

P0 does **not** mean:

- every downstream runtime lane is already closed
- all 3D/world results are production-grade
- local-core now owns provider-native runtime logic
