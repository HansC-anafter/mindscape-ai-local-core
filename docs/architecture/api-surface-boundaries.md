# API Surface Boundaries

Mindscape AI Local Core exposes local API surfaces for workspace state, governance, runtime configuration, meeting orchestration, tools, playbooks, objects, dispatch, and optional connectors.

This page describes the public API boundary for the current repository. It is not an endpoint reference.

## Registration Model

The FastAPI application delegates route registration to the application bootstrap layer. The bootstrap layer registers core routes, core primitives, feature-package routes, and optional connector routes.

The public boundary is the registration pattern and route families, not every private handler. Optional routers may be absent when dependencies, installed capabilities, or connector modules are unavailable.

## Core Local Route Families

Local Core route families include host surfaces for:

- workspace and workspace group state
- playbook and tool coordination
- retrieval, configuration, and integration adapters
- settings and runtime configuration
- vector-backed retrieval and review
- capability hosting and activation

These route families are Local Core host surfaces. Their public documentation should focus on stable contracts and boundaries, not provider payloads or capability implementation details.

## Workspace Runtime Routes

Workspace-scoped routes aggregate local workspace lifecycle, workbench state, task activity, health, meeting context, object runtime, runtime configuration, and governance surfaces.

Workspace routes are the main local runtime surface. Public documentation may describe workspace-scoped state, object runtime behavior, meeting graph access, governance review surfaces, and runtime configuration boundaries.

Public documentation must not expose local user data, workspace seed data, runtime logs, ignored backups, uploads, or private environment files.

## Object, Runtime, and Settings Routes

Object runtime routes are workspace-scoped. They expose bounded object discovery, selection, indexing, and host-mediated object operations through Local Core contracts.

Runtime environment routes and workspace runtime configuration routes describe local runtime choices and workspace-level runtime configuration. Settings extension routes expose host-owned configuration sections.

These routes are safe to document as host contracts. Capability-owned object schemas, resolver internals, materializer internals, and provider credentials remain outside the public Local Core scope.

## Governance, Lens, and Memory Routes

Workspace governance routes expose governed memory review, health, impact, decision, and metrics surfaces.

Lens routes expose local lens definition, runtime resolution, review, and evidence surfaces.

Vector routes support semantic retrieval and vector database configuration. Public documentation may describe these as governed retrieval and review surfaces. It must not present raw provider payload dumps, private receipt internals, or unrestricted memory export as stable public APIs.

## Playbook and Tool Routes

Playbook routes aggregate playbook discovery, intent support, tool binding, resource binding, and host lifecycle behavior.

Tool routes aggregate tool availability, connection state, execution coordination, retrieval, filtered selection, registry behavior, and adapter boundaries.

Public documentation may describe playbooks and tools as local execution interfaces. It must not document capability-owned playbook specs, provider-native credentials, or per-provider private payloads as Local Core architecture.

## Meeting, Dispatch, and Handoff Routes

Meeting session routes are workspace-scoped. Agent dispatch routes provide bounded task dispatch surfaces. Handoff bundle routes support host-mediated handoff intake and review.

MCP bridge and device-node routes are optional integration surfaces. They let Local Core accept or expose local work through sidecar and connector processes, but they do not make those connectors Local Core ownership.

## Capability API Loading

Capability API routes can be activated or loaded through host mechanisms. This is a Local Core host boundary, not a per-capability API release or router authoring guide.

Public Local Core docs may describe the host loader, activation policy, and boundary rules. They must not document individual capability routers, services, UI paths, provider payloads, or generated runtime artifacts as Local Core public APIs.

## Withheld API Material

The following API material remains withheld by default:

- unreleased endpoint references
- route examples that depend on capability internals
- provider-native payload schemas
- cloud-only business features
- private connector callback payloads
- ignored runtime data, backups, uploads, logs, and environment files
- internal reports, debug notes, implementation histories, and testing logs

An API page can move into public docs only after its route family has been checked against the current repository and rewritten as a stable external contract.

## Public Boundary

Local Core owns local API route registration, route family organization, workspace-scoped host contracts, governance review surfaces, runtime configuration surfaces, playbook and tool host interfaces, object runtime host contracts, dispatch and handoff intake surfaces, and optional connector adapters.

Local Core does not publicly own:

- individual capability service implementations
- capability-owned schemas or storage internals
- provider-specific credentials or payloads
- cloud account, billing, or tenant lifecycle
- private prompt or handler internals
- ignored or CI-protected implementation paths

Public API documentation should stay at the host-contract level unless a specific endpoint reference has been separately verified, stabilized, and cleared for external release.
