# Artifact Taxonomy

This document defines the public-safe artifact names used across the current Mindscape documentation.

The goal is simple:

- explain what readers can expect to see
- avoid forcing them to understand pack internals first
- keep provider-specific payloads out of the top-level product story

## Taxonomy Principles

1. Name artifacts by what they do for the operator.
2. Keep provider/runtime names out of page titles when possible.
3. Distinguish `preview`, `candidate`, and `production-ready`.
4. Treat runtime receipts and world summaries as first-class artifacts.

## Core Artifact Families

### TaskIR

- **Role**: bounded control-plane artifact
- **Used for**: execution-ready work, dependencies, dispatch boundaries
- **What it proves**: the meeting/runtime stack reached an execution-shaped decision
- **What it does not prove**: downstream runtime quality or provider-specific execution success

### SpatialSchedulingIR

- **Role**: bounded planning-plane artifact for spatial/world execution intent
- **Used for**: scene/subject/object/camera-aware planning, constraint summaries, downstream consumer hints
- **What it proves**: the workflow produced a reusable planning artifact rather than only one-off runtime payloads
- **What it does not prove**: every downstream consumer lane is implemented

### Preview Mesh

- **Role**: inspectable mesh artifact for preview, editing, or comparison
- **Typical public-safe language**: `single-image preview mesh`, `scene/person preview meshes`
- **What it proves**: structural operability and bounded artifact closure
- **What it does not prove**: final reconstruction quality

### Scene Package

- **Role**: structured scene artifact or artifact family that preserves scene identity and downstream handoff readiness
- **Typical public-safe language**: `scene package preview`, `fixed-scene continuity package`
- **What it proves**: scene identity can be packaged and reused
- **What it does not prove**: full downstream runtime ingest is universally closed

### Runtime Receipt

- **Role**: normalized execution outcome returned by a consumer runtime
- **Used for**: traceability, status, bounded outputs, artifact refs
- **What it proves**: the runtime completed a governed execution step
- **What it does not prove**: raw provider internals should be exposed to the host

### World Summary

- **Role**: bounded writeback artifact for continuity
- **Used for**: schedule summary, constraint summary, state summary, artifact refs, traceability keys
- **What it proves**: the host can remember outcome-level continuity
- **What it does not prove**: the host owns the runtime cache or raw geometry payloads

## Status Labels

Use these labels consistently:

| Label | Meaning | Do not imply |
| --- | --- | --- |
| `preview` | operator-inspectable or reviewable output | final production quality |
| `candidate` | contract gates or structural gates passed | visual or physical quality sign-off |
| `fallback` | bounded degraded lane used to keep the workflow closed | equivalence with the primary lane |
| `production-ready` | reserved for lanes with explicit quality, ops, and lifecycle sign-off | use this label casually |

## Writing Rules

### Prefer

- `single-image preview mesh`
- `fixed-scene subject swap`
- `scene package preview`
- `runtime receipt`
- `world summary`

### Avoid as first-layer naming

- provider-specific runtime names
- raw backend payload names
- internal adapter class names
- opaque job IDs without artifact meaning

## Example Caption Patterns

- `Single image to separate scene/person preview meshes`
- `Reuse one scene package while swapping the subject preview`
- `Current status: candidate preview artifact, not production-grade reconstruction`
- `Runtime receipt normalized back into a bounded world summary`
