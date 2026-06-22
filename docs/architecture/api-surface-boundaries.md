# API Surface Boundaries

Mindscape AI Local Core exposes local API surfaces for workspace state, governance, runtime configuration, meeting orchestration, tools, playbooks, objects, dispatch, and optional connectors.

This page describes the public API boundary for the current repository as a host-contract guide.

## Registration Model

The FastAPI application delegates route registration to the application bootstrap layer. The bootstrap layer registers core routes, core primitives, feature-package routes, and optional connector routes.

The public boundary is the registration pattern and route families. Handler-level details belong to the route owner and become public when a stable endpoint contract is released.

## Core Local Route Families

Local Core route families include host surfaces for:

- workspace and workspace group state
- playbook and tool coordination
- retrieval, configuration, and integration adapters
- settings and runtime configuration
- vector-backed retrieval and review
- capability hosting and activation

These route families are Local Core host surfaces. Their public documentation focuses on stable contracts, route ownership, and host boundaries.

## Workspace Runtime Routes

Workspace-scoped routes aggregate local workspace lifecycle, workbench state, task activity, health, meeting context, object runtime, runtime configuration, and governance surfaces.

Workspace routes are the main local runtime surface. Public documentation may describe workspace-scoped state, object runtime behavior, meeting graph access, governance review surfaces, and runtime configuration boundaries.

Public documentation describes route behavior through sanitized contracts, repository-backed landmarks, and bounded examples.

## Object, Runtime, and Settings Routes

Object runtime routes are workspace-scoped. They expose bounded object discovery, selection, indexing, and host-mediated object operations through Local Core contracts.

Runtime environment routes and workspace runtime configuration routes describe local runtime choices and workspace-level runtime configuration. Settings extension routes expose host-owned configuration sections.

These routes are public host contracts. Capability-owned object schemas, resolver internals, materializer internals, and credentials stay with their owners.

## Governance, Lens, and Memory Routes

Workspace governance routes expose governed memory review, health, impact, decision, and metrics surfaces.

Lens routes expose local lens definition, runtime resolution, review, and evidence surfaces.

Vector routes support semantic retrieval and vector database configuration. Public documentation describes these as governed retrieval and review surfaces tied to stable Local Core memory behavior.

## Playbook and Tool Routes

Playbook routes aggregate playbook discovery, intent support, tool binding, resource binding, and host lifecycle behavior.

Tool routes aggregate tool availability, connection state, execution coordination, retrieval, filtered selection, registry behavior, and adapter boundaries.

Public documentation describes playbooks and tools as local execution interfaces. Capability-owned playbook specs, credentials, and adapter payloads stay in owner documentation.

## Meeting, Dispatch, and Handoff Routes

Meeting session routes are workspace-scoped. Agent dispatch routes provide bounded task dispatch surfaces. Handoff bundle routes support host-mediated handoff intake and review.

MCP bridge and device-node routes are optional integration surfaces. They let Local Core accept or expose local work through sidecar and connector processes while connector implementation stays with the connector owner.

## Capability API Loading

Capability API routes can be activated or loaded through host mechanisms. This is the Local Core host boundary for activation and loading behavior.

Public Local Core docs describe the host loader, activation policy, and boundary rules. Individual capability routers, services, UI paths, adapter payloads, and generated runtime artifacts stay in owner-managed material.

## API Release Path

API material becomes public after its route family has been checked against the current repository and rewritten as a stable external contract. Candidate material includes:

- draft endpoint references
- route examples that depend on capability internals
- adapter payload schemas
- connector callback payloads
- ignored runtime data, backups, uploads, logs, and environment files
- operational reports, debug notes, implementation histories, and testing logs

## Public Boundary

Local Core owns local API route registration, route family organization, workspace-scoped host contracts, governance review surfaces, runtime configuration surfaces, playbook and tool host interfaces, object runtime host contracts, dispatch and handoff intake surfaces, and optional connector adapters.

Related owners keep:

- individual capability service implementations
- capability-owned schemas or storage internals
- credentials or adapter payloads
- account administration and managed service operations
- assembly details and handler internals
- ignored or CI-protected implementation paths

Public API documentation stays at the host-contract level. Specific endpoint references move into public docs after separate verification, stabilization, and external release review.
