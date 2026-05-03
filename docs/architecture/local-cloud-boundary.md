# Local and Cloud Boundary

Mindscape AI Local Core is the local-first runtime boundary. It can connect to external control planes and execution systems, but its public architecture must not be rewritten around any one external deployment.

This document defines the released public boundary for the current repository state.

## Boundary Principle

Local Core owns local governance, local workspace state, local orchestration, local execution state, capability hosting boundaries, and local artifacts.

External systems may coordinate or route work, but they remain integration peers or control-plane callers. They must not become the source of truth for Local Core architecture.

## What Local Core Owns

Local Core owns:

- workspace runtime and workspace-scoped state
- local workspace grouping surfaces
- intent, governance, lens, and memory services
- meeting orchestration and TaskIR compilation
- TaskIR persistence and dispatch state
- playbook execution and local tool execution
- capability hosting interfaces, activation state, and runtime shells
- sandboxed local artifacts
- optional connector adapter surfaces

## What External Systems May Own

External systems may own non-local responsibilities such as:

- account, organization, or billing lifecycle
- hosted deployment, scheduling, or distribution
- remote execution infrastructure
- cross-device coordination
- external messaging or publishing channels

External concerns can appear in Local Core as compatibility metadata or adapter parameters. Their presence does not make them Local Core ownership.

## Compatibility Fields Are Not Ownership

The current repository includes compatibility fields and headers used by external integration envelopes.

That is an integration reality, not a public ownership transfer. Public documentation must distinguish:

- local runtime ownership
- external compatibility metadata
- provider-specific payloads
- capability-specific data models

Compatibility metadata can be carried through Local Core when needed, but it must not redefine the local architecture.

## Capability Boundary

Installed capabilities may include provider-specific code, schemas, tools, API routes, and UI surfaces. Local Core hosts installed capabilities and exposes runtime shells for them.

Capability internals are not the same thing as Local Core architecture. A capability can depend on provider-specific or external-system-aware data, but that data should remain capability-owned unless it is promoted into a stable Local Core contract. Individual capability service implementations stay outside the public Local Core scope.

## Connector Boundary

The repository includes connector-facing surfaces for synchronization, remote execution, external agent coordination, and MCP-compatible tool exposure.

Connector code should be treated as adapters around Local Core:

- inbound connectors can submit or resume local work through host contracts
- outbound connectors can report bounded status, receipts, or events
- neither direction should require changing the core local workspace model for one external platform

Implementation details for Docker-ignored connector services, provider adapters, callback payloads, and remote protocols are not part of the public Local Core documentation scope. Public docs may name the adapter boundary only when the description remains independent of external implementation behavior.

## Public Documentation Rule

When releasing public documentation:

- describe Local Core as local-first and connector-capable
- keep account, tenant, billing, and provider details out of Local Core architecture pages
- treat compatibility fields as adapter metadata unless a stable Local Core contract says otherwise
- do not publish external implementation notes as Local Core architecture
- do not publish installed capability internals as Local Core architecture
- do not publish per-capability service implementations as Local Core architecture
- withhold ignored, Docker-ignored, and CI-protected implementation paths by default

## Current Release Scope

This page is a boundary statement, not an API reference. It does not release external connector protocol details, remote execution callback schemas, private authoring contracts, or external tenant implementation notes.
