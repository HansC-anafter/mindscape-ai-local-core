# Mindscape AI: Governed Memory Fabric

> This document describes the current public architecture story for memory in Mindscape AI. It supersedes the older "Event -> Intent -> Memory/Embedding" framing as the primary explanation of how long-term continuity works in Local-Core.

**Last Updated**: 2026-03-25  
**Status**: Public architecture direction

---

## Overview

Mindscape treats memory as part of long-term continuity and agent cognition.

The current architecture direction is:

> **Mindscape Operating Engine = Meeting Runtime + Governed Memory Fabric, under Governance Context, driving Actuation Layer**

Where:

- **Governance Context** = Intent + Mind-Lens + Policy
- **Meeting Runtime** = live deliberation, convergence, dispatch, and loop closure
- **Governed Memory Fabric** = long-term continuity, evidence, promotion, invalidation, and serving
- **Actuation Layer** = Project / Flow + Playbooks / Tools + Sandbox / external runtimes

This is why memory in Mindscape is part of the agent core.

---

## Why This Replaces the Older Story

The older public explanation was useful when the system was mostly organized as:

- event recording
- intent analysis
- embeddings / memory retrieval

But that framing is now too shallow for the product direction.

Mindscape needs to support:

- long-lived projects
- visible thinking
- human-governable AI execution
- decision continuity across sessions
- memory promotion, revision, and invalidation

That requires a memory model that can answer more than:

- "what text looks similar to this query?"

It also needs to answer:

- what has been repeatedly validated?
- what only applies in a certain context?
- what is still unresolved tension rather than stable memory?
- what has been revised or superseded?
- what belongs to interface self vs core self?

---

## The Four-Part Architecture

## 1. Governance Context

Governance Context answers:

- what matters?
- how should the system see and trade off?
- what cannot be violated?

It is mainly composed of:

- **Intent**: what the work is trying to achieve
- **Mind-Lens**: how to interpret, render, and prioritize
- **Policy**: constraints, approvals, and hard boundaries

This context shapes both meeting-time reasoning and memory-time serving.

## 2. Meeting Runtime

The Meeting Runtime is the live cognitive runtime of Mindscape.

Its responsibilities include:

- deliberation
- clarification
- convergence
- dispatch planning
- loop closure
- reflection handoff

It is where short-horizon thinking happens.

## 3. Governed Memory Fabric

The Governed Memory Fabric is the long-horizon continuity layer.

Its responsibilities include:

- preserving evidence
- compressing episodes
- promoting durable memory
- revising or invalidating outdated memory
- serving the right memory packet back into execution

It operates as a governed memory model for continuity, revision, and serving.

## 4. Actuation Layer

The Actuation Layer turns cognition into work in the world.

It includes:

- Project / Flow
- Playbooks
- Tools
- Sandbox
- External runtimes

This is where plans become artifacts, side effects, and decisions.

---

## Memory Planes

The public memory architecture is best understood as several planes sharing one contract.

### Signal / Event Plane

What just happened:

- conversations
- tool calls
- execution events
- reasoning traces
- artifact mutations

### Episodic Plane

Compressed experience units:

- session digests
- decision episodes
- tension episodes
- artifact milestones
- unresolved loops

### Interface Plane

Context-facing self and operating surfaces:

- role-conditioned behavior
- workspace / project identity surfaces
- lens-shaped interaction patterns

### Core Plane

Slower-moving durable state:

- preferences
- principles
- anti-goals
- deep priors
- stable reward tendencies

### Procedural Plane

Preferred ways of doing work:

- how a meeting should close
- how ambiguity should be handled
- what "done" means for an artifact
- what recurring workflow patterns are preferred

### Serving Plane

The serving plane is how memory gets routed back into execution:

- vector search
- graph traversal
- symbolic filters
- recency / importance / evidence ranking

Important:

> Retrieval belongs to the serving plane. It does not define memory itself.

---

## Write Boundaries

Mindscape does not treat all events as equal.

Formal canonical write boundaries are the moments where memory formation should happen deliberately:

- meeting close
- meta meeting close / reflection meeting close

Workflow outcomes such as artifact milestones, reasoning traces, governance receipts, and execution traces are evidence intake surfaces in the current rollout.
They can be brought into deliberation and attached to governed memory, but they do not independently create canonical memory items outside meeting-time or meta-meeting-time closure.

Without explicit write boundaries, memory collapses back into logs and prompt stuffing.

---

## Relationship to Current Local-Core Implementation

The architecture direction above does not assume a blank slate.

Local-Core already has meaningful pieces of this model:

- **Meeting Runtime substrate**:
  - session close
  - digest extraction
  - convergence / dispatch logic
  - state vectors and follow-up governance

- **Memory substrate**:
  - workspace / project / member memory surfaces
  - `SessionDigest`
  - `PersonalKnowledge`
  - `GoalLedger`
  - `ReasoningTrace`
  - vector-backed semantic serving

The current direction is not to throw these away. It is to converge them into a clearer model:

- existing layered memories become **surfaces / projections**
- episodic and governed writeback become first-class
- vector embeddings remain a **serving layer**
- memory objects, evidence, lifecycle, and versions become more explicit

---

## Design Principles

1. **Memory is governed state with searchable projections**
2. **Embeddings are projections; canonical memory remains explicit**
3. **Evidence comes before promotion**
4. **Write boundaries must be explicit**
5. **Memory must support revision, supersession, and invalidation**
6. **Meeting Runtime and Memory Fabric together form the cognitive core**

---

## Relationship to Legacy Documentation

The older event / intent / memory-embedding explanation is still useful as historical implementation context.

See:

- [Legacy Event, Intent, and Memory/Embedding Architecture](./memory-intent-architecture.md)

That document remains valuable for the earlier event and intent pipeline, but the architecture philosophy for public understanding is now the Governed Memory Fabric described here.
