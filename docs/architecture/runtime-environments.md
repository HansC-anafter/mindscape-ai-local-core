# Runtime Environments and AOL Runtime

Mindscape AI Local Core hosts runtime surfaces through a local-first registry, workspace runtime routes, settings discovery, and optional adapters. This page describes the released public architecture scope for the current repository.

## Runtime Registry

Local Core exposes a local runtime environment registry. The registry combines built-in runtime definitions with user-defined runtime records and stores metadata needed by the local console and dispatch layers.

The registry is a local management surface. Local Core keeps workspace ownership in the local host while adapter records point to surrounding runtimes.

## Runtime Authentication and Proxying

Runtime authentication and approved configuration relay are handled through local host services.

These services let Local Core connect to external runtimes while secrets stay behind host services. Public documentation describes this as host-mediated runtime access.

## Settings Extensions

Local Core discovers settings extensions from installed capability manifests and built-in runtime definitions. The settings extension surface exposes runtime and service configuration sections for the local console while keeping capability-specific settings owned by the capability that declares them.

Settings discovery is the public console-facing discovery layer for already installed local surfaces. Capability authoring details stay with the capability owner.

## Workspace Runtime Scope

Workspace runtime surfaces own local workspace state, workspace files, tasks, activity, governance routes, runtime configuration, and capability surfaces that run inside the local workspace.

Workspace runtime configuration can carry compatibility metadata for external systems. That metadata remains adapter data before promotion into a stable Local Core contract.

## Host Runtime Sessions

Local Core can record host runtime sessions as workspace-owned state. A session carries runtime surface identity, turns, events, governance references, and bridge status so the workspace can show what a host-side runtime is doing.

The host runtime process still owns execution. Local Core owns the local session record, event stream, review surface, and bridge registration needed to make that execution visible and governable.

## Resource Lanes and Queue Visibility

Local runtime execution is also bounded by host resource lanes and runner queues. Local Core can expose lane metadata, queue utilization, workspace allocations, route intent previews, route reservations, runner claim gates, and spillover status.

This is local capacity governance. Queue and runner internals become public only when promoted into a stable host contract.

## AOL Runtime

The Addressable Object Layer runtime is implemented through workspace-scoped host surfaces and frontend shell components. It gives installed capability surfaces a common way to expose concrete objects, selections, meeting context, materialization, and graph projections.

The backend runtime covers object discovery, indexing, search, selection, action coordination, meeting attachment, materialization coordination, and bounded graph projection. These are host contracts; capability-owned object schemas and materializer internals remain outside public Local Core scope.

The frontend includes host shell surfaces that let workspace capability pages participate in object targeting and meeting attachment flows through shared Local Core UI contracts.

## Optional Runtime Adapters

The repository also contains optional adapter-facing surfaces for external coordination, remote execution, external agent adapters, host sidecar services, and MCP-compatible tool exposure. These adapters sit around Local Core as integration points.

Adapter implementation details, callback schemas, payloads, and Docker-ignored connector services stay with the adapter owner.

## Public Boundary

Local Core owns the runtime registry, local runtime access mediation, workspace runtime surfaces, host runtime session state, local resource capacity visibility, AOL object identity transport, local meeting attachment, local materialization coordination, and local graph projection.

Related owners keep:

- external runtime account administration
- account administration and managed service operations
- adapter runtime payload schemas
- raw queue, worker, and sidecar process internals
- installed capability implementation details
- connector-specific callback schemas

Public runtime documentation describes stable local contracts, adapter boundaries, and source-backed host behavior.
