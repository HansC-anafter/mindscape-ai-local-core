# Local Boundary and External Interfaces

Mindscape AI Local Core is the local runtime boundary for governed AI work. It keeps workspace state, governance context, orchestration, memory, dispatch state, runtime sessions, capability host shells, and artifacts inside the local host model.

This page explains how Local Core stays locally owned while still accepting integration through explicit host and adapter contracts.

## Local Ownership

Local Core owns the behavior a local operator can inspect and control from this repository:

- workspace runtime and workspace-scoped state
- local workspace grouping surfaces
- intent, governance, lens, and memory services
- meeting orchestration and TaskIR compilation
- TaskIR persistence and dispatch state
- playbook execution and local tool execution
- capability hosting interfaces, activation state, and runtime shells
- sandboxed local artifacts
- adapter entry points for external coordination

In everyday terms, Local Core is the local workbench and control room. It stores the work, prepares the context, records what happened, exposes local capacity, and gives installed capabilities a stable place to appear.

## External Interfaces

External systems can coordinate, request, resume, or observe local work through adapter contracts. Local Core treats those systems as integration peers around the local host.

The stable public idea is simple: external systems may pass work into Local Core, but the local workspace model remains the source of truth for local state, governance evidence, runtime sessions, and dispatch records.

## Compatibility Metadata

Local Core can carry compatibility metadata when an adapter needs it. That metadata helps route or resume work across boundaries while the local host keeps its own workspace, task, object, and memory identities.

Public documentation should describe compatibility metadata as adapter context. Stable Local Core models stay centered on local workspace state, local governance state, object identity, runtime sessions, and TaskIR records.

## Capability Boundary

Installed capabilities can bring their own schemas, tools, routes, UI pages, and service logic. Local Core hosts the parts that need to appear in the workspace: discovery, activation, shell placement, shared controls, tool rails, object targeting, policy gates, and dispatch gates.

The public Local Core contract is the host behavior. Capability implementation material belongs to the capability owner until a shared behavior is promoted into a stable Local Core interface.

## Connector Boundary

Connector-facing code surrounds Local Core with synchronization, remote execution, external agent coordination, host sidecar, and MCP-compatible tool exposure surfaces.

The public contract is the adapter shape:

- inbound adapters submit or resume local work through host contracts
- outbound adapters report bounded status, receipts, or events
- sidecar and gateway surfaces connect local work to surrounding systems through explicit registration and callback boundaries

Public docs can name these adapter roles when the description stays independent of a specific external deployment.

## Public Documentation Standard

Public Local Core pages should lead with local behavior:

- what the local host owns
- what a user or operator can inspect
- which host contract carries the work
- which adapter contract connects surrounding systems
- which owner keeps capability or connector implementation details

This keeps formal Local Core documentation centered on the local runtime while still explaining how integration works.
