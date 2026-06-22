# Capability Hosting Boundary

Mindscape AI Local Core hosts installed capabilities through stable local host contracts.

This page defines the public documentation boundary for capability-related material in the current repository.

## Boundary Statement

Local Core owns the host boundary around capabilities. Capability owners keep their internal service implementation, schemas, UI pages, and execution details.

Local Core owns:

- capability discovery and activation state needed by the local runtime
- capability runtime shells exposed through the local workspace
- workspace-scoped capability UI host shells and shared workspace tool rails
- settings extension discovery for already installed local surfaces
- tool, playbook, object, and artifact host interfaces that are promoted into stable Local Core contracts
- policy, dispatch, and executor gates that decide whether a requested action can run
- local routing and registry surfaces that keep the host aware of installed capabilities

Capability-owned material includes:

- per-capability backend service code
- per-capability frontend UI implementation
- adapter schemas, payloads, and credentials
- capability-specific playbook specs and assembly material
- capability-specific storage models and migrations
- capability-specific business rules, validation rules, and execution details

Public Local Core documentation describes the host interface and links capability material through ownership boundaries.

## Repository Guardrails

The repository guardrails reinforce this boundary.

The Git ignore rules exclude local data, generated artifacts, credentials, runtime bundles, installed capability directories, installed playbook directories, capability-installed model directories, and internal material.

The Docker build ignore rules exclude capability installation locations, external playbook locations, provider and sync service mirrors, internal material, local data, logs, environment files, and temporary files from the local image context.

The CI guardrails protect capability boundaries, external component leakage, remote-function leakage, route conflicts, manifest validity, import path validity, router prefix validity, and root-level script boundaries.

Guardrail-protected material stays in owner-managed records until it is promoted into a stable Local Core contract and released through source-backed documentation.

## Documentation Rule

Public Local Core docs may document:

- capability hosting contracts
- runtime shell behavior
- workspace capability UI host behavior
- shared workspace and pack-scope tool rail behavior
- stable host registry, object, tool, and playbook interfaces
- dispatch and policy boundaries
- host-level activation state and guardrail behavior

Owner-managed capability material includes:

- individual capability service implementations
- ignored runtime artifacts or generated bundles
- ignored local data, uploads, logs, backups, or environment files
- operational reports, work plans, debug notes, implementation histories, and testing logs
- credentials, request payloads, or account setup
- external business features owned by surrounding systems
- capability-specific UI, playbook, schema, migration, or storage internals

## Workspace UI Host Boundary

Local Core owns the workspace shell that hosts capability UI. The shell supplies workspace context, common tool rails, responsive framing, object-aware host services, runtime panels, and shared navigation behavior.

The capability owns the UI implementation inside that shell. Public Local Core docs describe the host shell, shared controls, and workspace contracts.

Candidate public pages describe the stable host boundary represented by Local Core contracts. Owner-managed implementation material stays with the capability package.

## Public Boundary

Local Core owns capability hosting boundaries and shared host behavior.

This means Local Core can document how installed capabilities are discovered, surfaced, hosted, gated, and invoked through stable host contracts.

A capability detail becomes public Local Core architecture when it has been promoted into a stable Local Core contract and verified against the current repository.
