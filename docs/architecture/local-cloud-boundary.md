# Local and Cloud Boundary

Mindscape AI Local Core is the local-first runtime boundary. It can connect to external control planes and execution systems, but its public architecture should not be rewritten around any one cloud deployment.

This document defines the released public boundary for the current repository state.

## Boundary Principle

Local Core owns local governance, local workspace state, local orchestration, local execution state, capability hosting boundaries, and local artifacts.

Cloud systems may coordinate, provision, meter, or route work, but they must remain integration peers or control-plane callers. They must not become the source of truth for Local Core's internal architecture.

## What Local Core Owns

Local Core owns:

- workspace runtime and workspace-scoped state
- local workspace groups and group compatibility views
- intent, governance, lens, and memory services
- meeting orchestration and TaskIR compilation
- TaskIR persistence and dispatch state
- playbook execution and local tool execution
- capability hosting interfaces, activation state, and runtime shells
- sandboxed local artifacts
- optional connector services that call out or accept callbacks

## What Cloud Systems May Own

Cloud systems may own:

- cloud account and tenant lifecycle
- organization-level policy and billing
- cloud-hosted deployment, scheduling, and distribution
- remote execution infrastructure
- cross-device coordination
- external messaging or publishing channels

Cloud-owned concerns can appear in Local Core as compatibility fields, connector parameters, callback payloads, or adapter metadata. Their presence does not make them Local Core ownership.

## Compatibility Fields Are Not Ownership

The current repository includes compatibility fields and headers used by cloud or integration envelopes, including tenant-like and group-like identifiers in some models, routes, migrations, playbook inputs, and frontend context types.

That is an integration reality, not a public ownership transfer. Public documentation must distinguish:

- local runtime ownership
- cloud compatibility metadata
- provider-specific payloads
- capability-specific data models

Compatibility metadata can be carried through Local Core when needed, but it must not redefine the local architecture.

## Capability Boundary

Installed capabilities may include provider-specific code, schemas, tools, API routes, and UI surfaces. Local Core hosts installed capabilities and exposes runtime shells for them.

Capability internals are not the same thing as Local Core architecture. A capability can depend on provider-specific or cloud-aware data, but that data should remain capability-owned unless it is promoted into a stable Local Core contract. Individual capability service implementations stay outside the public Local Core scope.

## Connector Boundary

The repository includes connector surfaces for cloud synchronization, remote execution callbacks, external agents, and MCP-compatible tool exposure.

Connector code should be treated as adapters around Local Core:

- inbound connectors can submit or resume local work
- outbound connectors can report status, receipts, or events
- neither direction should require changing the core local workspace model for one cloud platform

## Public Documentation Rule

When releasing public documentation:

- describe Local Core as local-first and connector-capable
- keep cloud-specific account, tenant, billing, and provider details out of Local Core architecture pages
- treat compatibility fields as adapter metadata unless a stable Local Core contract says otherwise
- do not publish cloud implementation notes as Local Core architecture
- do not publish installed capability internals as Local Core architecture
- do not publish per-capability service implementations as Local Core architecture
- withhold ignored, Docker-ignored, and CI-protected implementation paths by default

## Current Release Scope

This page is a boundary statement, not an API reference. It does not release cloud connector protocol details, remote execution callback schemas, internal authoring contracts, or tenant-specific implementation notes.
