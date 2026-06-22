# Host Runtime, Resource Control, and Workspace UI Hosting

Mindscape AI Local Core starts local work and keeps it bounded: which runtime can take a task, which queue or lane it belongs to, whether the workspace has an allocation, what the current capacity looks like, and how capability surfaces are hosted inside the workspace.

This page describes the released public architecture scope for host runtime, local resource control, and workspace-hosted capability UI.

## Host Runtime Sessions

Local Core can keep a workspace-scoped record of a host runtime session. A session is the local record of an interactive runtime surface, its turns, its events, and the governance references attached to each turn.

The runtime process still owns its own execution. Local Core owns the workspace session record, event stream, bridge registration, approval/audit surface, and the reviewable state that the workspace can show.

Publicly, this means Local Core can expose host runtime work as workspace-owned progress instead of treating a host-side process as an invisible side effect.

## Resource Lanes and Queue Visibility

Local Core uses resource lanes to describe local execution capacity in a way the workspace can reason about. A lane can represent runner capacity, a browser-oriented execution pool, a vision runner, or a dynamically declared local lane.

Queue visibility is deliberately low-cardinality. The host can report queue depth, runner capacity, utilization, freshness, backlog summaries, and degraded-state errors through stable public fields.

This is the public behavior: users and operators can see whether local work is waiting, running, blocked, or capacity-limited from Local Core host surfaces.

## Workspace Allocation and Admission

Workspace allocations let Local Core decide how a workspace can use a host resource lane. They can carry lane, queue, task-family, concurrency, worker target, priority, and policy information.

Admission preview and route intent preview are host-level decision surfaces. They answer whether a piece of local work appears eligible for a route before it consumes worker capacity.

Public documentation describes this as local capacity governance. Worker scheduling internals stay in implementation records until promoted into a stable host contract.

## Runner Claim and Spillover Controls

Runner claim controls let the host pause, resume, or limit which runners can claim work. Spillover controls let the host reason about overflow behavior when local demand exceeds the preferred lane.

The stable public boundary is the control responsibility: Local Core owns the host-level gate and visible status; individual worker implementations remain internal.

## Workspace Capability UI Host

Installed capability UI is hosted through workspace-scoped shells. The shell gives the capability surface a workspace context, shared tool rails, optional runtime panels, responsive workbench framing, and object-aware host services.

The shell is Local Core architecture. The capability UI implementation inside that shell remains capability-owned. Public docs describe the host shell, route shape, shared rails, and object/runtime integration points.

## Inline Object References

Workspace UI can render object references inline and ask the local object runtime for a bounded preview. When indexing is still pending, the preview path may request a bounded sync before trying the read again.

This makes object references useful in workspace review surfaces while owner-managed object state stays with the object owner.

## Host Sidecar Service Proxies

Local Core can proxy selected host-side services such as speech, voice, or capture relay helpers. These proxies report availability and structured errors through Local Core, while the sidecar service owns the device-specific or process-specific work.

The public contract is mediation and error handling. Device setup, media relay internals, adapter payloads, and credentials stay with the sidecar or capability owner.

## Public Boundary

Local Core owns:

- workspace-owned host runtime sessions, turns, event streams, and bridge registration
- host resource lanes, queue utilization projections, workspace allocations, route intent previews, route reservations, runner claim gates, and spillover status
- workspace-scoped capability UI hosting, shared tool rails, responsive workbench framing, and object-aware shell integration
- mediated host sidecar service access and structured unavailable/error states

Related owners keep:

- external runtime process internals
- raw queue, Redis, worker, or adapter payload details
- capability-owned UI implementation
- device-specific service setup
- operational logs, rollout plans, or validation captures

Public docs describe stable host responsibilities and user-visible boundaries. Low-level scheduling internals, sidecar payloads, capability implementation details, and operational evidence stay in owner-managed records.
