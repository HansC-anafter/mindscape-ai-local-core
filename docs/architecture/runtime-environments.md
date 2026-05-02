# Runtime Environments and AOL Runtime

Mindscape AI Local Core hosts runtime surfaces through a local-first registry, workspace runtime routes, settings discovery, and optional adapters. This page describes the released public architecture scope for the current repository.

## Runtime Registry

Local Core exposes a runtime environment registry at `/api/v1/runtime-environments`. The registry combines built-in runtime definitions with user-defined runtime records and stores runtime metadata such as name, icon, configuration URL, authentication type, dispatch support, cell support, and dispatch recommendation flags.

The registry is a local management surface. It does not make an external runtime the owner of Local Core workspace state.

## Runtime Authentication and Proxying

Runtime authentication is handled through local services and routes:

- `/api/v1/runtime-oauth` starts and completes OAuth flows for configured runtime providers.
- `/api/v1/runtime-proxy` forwards approved runtime configuration requests after checking access and injecting the selected runtime authentication headers.
- Runtime auth configuration is resolved through stored runtime configuration, system settings, and environment fallback where supported.

These routes let Local Core connect to external runtimes without exposing runtime secrets directly to the frontend.

## Settings Extensions

Local Core discovers settings extensions from installed capability manifests and built-in runtime definitions. The settings extension route exposes runtime and service configuration sections for the local console while keeping capability-specific settings owned by the capability that declares them.

Settings discovery is not a capability authoring contract. It is the public console-facing discovery layer for already installed local surfaces.

## Workspace Runtime Scope

Workspace routes are mounted under `/api/v1/workspaces`. The workspace runtime owns local workspace state, workspace files, tasks, activity, governance routes, runtime configuration, and capability surfaces that run inside the local workspace.

Workspace runtime configuration can carry compatibility metadata for external systems, but that metadata remains adapter data unless a stable Local Core contract promotes it.

## AOL Runtime

The Addressable Object Layer runtime is implemented as workspace-scoped routes and frontend shell components. It gives installed capability surfaces a common way to expose concrete objects, selections, meeting context, materialization, and graph projections.

The backend runtime includes routes for:

- object catalog discovery
- object instance indexing, sync, search, read, and mention completion
- object relation indexing and relation search
- UI selection resolution into stable object references
- contextual object action planning, invocation, and closure
- object attachment into meeting sessions
- materialization of object outcomes through owner capability backends
- object graph projection with persisted relation fallback

The frontend includes the addressable-object host provider, host shell components, and meeting bottom shell surfaces that let workspace capability pages participate in object targeting and meeting attachment flows.

## Optional Runtime Adapters

The repository also contains optional connector surfaces for cloud coordination, remote execution callbacks, external agent adapters, and MCP-compatible tool exposure. These adapters sit around Local Core and should be described as integration points, not as core ownership boundaries.

## Public Boundary

Local Core owns the runtime registry, local runtime authentication mediation, workspace runtime routes, AOL object identity transport, local meeting attachment, local materialization coordination, and local graph projection.

Local Core does not publicly own:

- external runtime account administration
- cloud tenant lifecycle
- provider-native runtime payload schemas
- installed capability implementation details
- connector-specific callback schemas

Public runtime documentation should describe stable local contracts and adapter boundaries. It should not publish internal migration notes, unreleased setup flows, provider secrets, or capability implementation plans.
