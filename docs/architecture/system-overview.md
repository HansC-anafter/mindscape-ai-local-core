# System Overview

Mindscape AI Local Core is the local-first runtime host for governed AI work. It combines workspace state, conversation intake, governance context, meeting orchestration, memory, playbook execution, tools, sandboxed artifacts, and optional runtime connectors.

This page is a public overview. It is intentionally smaller than the internal architecture notes and avoids unreleased APIs, private validation material, and implementation history.

## Current Runtime Shape

At a high level, Local Core is organized as:

```text
Workspace UI / API / external surface
  -> workspace and conversation routes
  -> governance context, intent, lens, and memory services
  -> meeting and orchestration services
  -> TaskIR and dispatch orchestration
  -> playbooks, tools, capability hosting boundaries, sandboxes, and optional connectors
  -> artifacts, traces, receipts, and memory writeback
```

## Verified Public Components

### Workspace Host

The workspace host is the primary local container for user-visible work. It owns workspace CRUD, workspace files, activity, tasks, workbench surfaces, runtime metadata, object runtime routes, governance routes, and workspace group compatibility surfaces.

The public contract is local-first: users can run the workspace host without depending on a cloud control plane.

### Governance Context

Governance context is the layer that carries intent, policy, lens, and memory selection into execution. In the current repository this is represented across intent services, governance services, lens services, and conversation context builders.

The public point is not that every governance feature is a single module. The public point is that execution is not treated as raw prompt dispatch; it is routed through context, policy, and traceable state.

### Meeting Runtime

The meeting runtime is the orchestration layer for deliberation, semantic normalization, dispatch gating, TaskIR compilation, and supervision. It is present in the repository as meeting-oriented orchestration services rather than as a separate product boundary.

The meeting runtime can compile structured work for downstream dispatch. It should be described publicly as a governance and convergence layer, not as provider-specific automation.

### TaskIR and Dispatch

`TaskIR` is the structured execution artifact used by Local Core to represent executable work, phases, dependencies, status, artifacts, checkpoints, and dispatch metadata.

Dispatch orchestration consumes compiled TaskIR phases and routes them into local execution paths such as playbooks, tools, capability host interfaces, external runtimes, and sandbox-backed work.

### Memory and Writeback

Local Core has workspace, project, and member memory services, plus meeting memory writeback services and world-memory support modules. Public documentation should describe this as governed memory and continuity, not as an unrestricted dump of provider payloads.

The durable public claim is: memory and writeback exist to preserve continuity, evidence, and reviewable state across runs.

### Lens

Mind-Lens services resolve, compose, compile, and apply viewpoint or style context. Public documentation should present this as a user-controlled interpretation layer that shapes execution behavior.

### Playbooks, Tools, Capability Hosting, and Sandboxes

Local Core includes playbook models and execution routes, tool registries and providers, capability hosting boundaries, and sandbox services. These are local actuation surfaces. They should remain clearly separated from the governance and meeting layers in public documentation.

Capability authoring details and per-capability service implementations are not Local Core public architecture.

### Optional Connectors

The repository includes local connector surfaces such as cloud connector services, remote execution callback routes, external agent adapters, and an MCP gateway package. These surfaces should be described as optional integration points.

They do not make the local workspace dependent on a cloud product.

## Public Boundary

Local Core owns:

- local workspace runtime
- governance context and local memory continuity
- meeting orchestration and dispatch compilation
- TaskIR-based execution state
- local playbooks, tools, capability hosting contracts, and sandboxed artifacts
- optional connectors that adapt local execution to external systems

Local Core should not be documented as owning:

- a cloud product's tenant lifecycle
- billing, SaaS plans, or account administration
- provider-native runtime payloads as canonical memory
- installed capability internals as core architecture
- per-capability service implementations

## What Remains Withheld

The following content is intentionally not released here:

- unreleased API references
- private validation material
- scenario deep dives
- historical architecture notes
- internal implementation plans
- per-capability service implementation details
- installed capability development guides
- old playbook publishing instructions
