# System Overview

Mindscape AI Local Core is the local-first runtime host for governed AI work. It combines workspace state, conversation intake, governance context, meeting orchestration, memory, playbook execution, tools, sandboxed artifacts, and optional runtime connectors.

This page is the public overview for the current repository. It summarizes released Local Core behavior and keeps owner-specific implementation records in their owning documentation sets.

## Current Runtime Shape

At a high level, Local Core is organized as:

```text
Workspace UI / API / external surface
  -> workspace and conversation routes
  -> governance context, intent, lens, and memory services
  -> meeting and orchestration services
  -> TaskIR and dispatch orchestration
  -> host runtime sessions, resource lanes, queue visibility, and workspace capacity controls
  -> playbooks, tools, capability hosting boundaries, sandboxes, and optional connectors
  -> artifacts, traces, receipts, and memory writeback
```

## Verified Public Components

### Workspace Host

The workspace host is the primary local container for user-visible work. It owns workspace CRUD, workspace files, activity, tasks, workbench surfaces, runtime metadata, object runtime routes, governance routes, and workspace group compatibility surfaces.

The public contract is local-first: users can run the workspace host from the local stack and connect surrounding systems through explicit adapter contracts.

### Governance Context

Governance context is the layer that carries intent, policy, lens, and memory selection into execution. In the current repository this is represented across intent services, governance services, lens services, and conversation context builders.

The public point is that execution is routed through context, policy, and traceable state before work reaches dispatch.

### Meeting Runtime

The meeting runtime is the orchestration layer for deliberation, semantic normalization, dispatch gating, TaskIR compilation, and supervision. It is present in the repository as meeting-oriented orchestration services rather than as a separate product boundary.

The meeting runtime can compile structured work for downstream dispatch. Public docs describe it as the governance and convergence layer that turns discussion into reviewable execution state.

### TaskIR and Dispatch

`TaskIR` is the structured execution artifact used by Local Core to represent executable work, phases, dependencies, status, artifacts, checkpoints, and dispatch metadata.

Dispatch orchestration consumes compiled TaskIR phases and routes them into execution paths such as playbooks, tools, capability host interfaces, adapter-mediated runtimes, and sandbox-backed work.

### Host Runtime and Resource Control

Local Core keeps local runtime work visible as workspace-owned state. Host runtime sessions record interactive runtime turns and events, while bridge registration lets a host-side runtime connect through the local host contract.

Local Core also exposes host resource lanes, queue visibility, workspace allocations, route intent previews, route reservations, runner claim controls, and spillover status. The public point is capacity governance: local work should be visible, bounded, and reviewable before it consumes runner capacity.

### Memory and Writeback

Local Core has workspace, project, and member memory services, plus meeting memory writeback services and world-memory support modules. Public documentation describes this as governed memory and continuity: memory is reviewed, sourced, and tied back to execution evidence.

The durable public claim is: memory and writeback exist to preserve continuity, evidence, and reviewable state across runs.

### Lens

Mind-Lens services resolve, compose, compile, and apply viewpoint or style context. Public documentation should present this as a user-controlled interpretation layer that shapes execution behavior.

### Playbooks, Tools, Capability Hosting, and Sandboxes

Local Core includes playbook models and execution routes, tool registries and providers, capability hosting boundaries, and sandbox services. These are local actuation surfaces. Public documentation keeps them clearly separated from the governance and meeting layers.

Capability authoring details and per-capability service implementations stay with the capability owner. Shared behavior moves into Local Core documentation after becoming a stable host contract.

### Optional Connectors

The repository includes local connector surfaces such as external connector services, remote execution callback routes, external agent adapters, and an MCP gateway package. These surfaces are optional integration points around the local host.

The local workspace model remains centered on local state, governance evidence, runtime sessions, and TaskIR records.

## Public Boundary

Local Core owns:

- local workspace runtime
- governance context and local memory continuity
- meeting orchestration and dispatch compilation
- TaskIR-based execution state
- host runtime sessions and local capacity controls
- local playbooks, tools, capability hosting contracts, and sandboxed artifacts
- optional connectors that adapt local execution to external systems

Related systems own:

- account administration and managed service operations
- deployment, distribution, and remote execution operations
- capability implementation details and storage internals
- adapter payloads and transport details
- generated operational evidence and release records

## Owner-Managed Material

The following material belongs in owner-managed documentation until promoted into stable Local Core contracts:

- draft API references
- validation captures
- scenario deep dives
- historical architecture notes
- internal implementation plans
- per-capability service implementation details
- installed capability development guides
- old playbook publishing instructions
