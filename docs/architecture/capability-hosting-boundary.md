# Capability Hosting Boundary

Mindscape AI Local Core can host installed capabilities, but capability internals are not Local Core architecture.

This page defines the public documentation boundary for capability-related material in the current repository.

## Boundary Statement

Local Core owns the host boundary around capabilities. It does not own each capability's internal service implementation.

Local Core owns:

- capability discovery and activation state needed by the local runtime
- capability runtime shells exposed through the local workspace
- settings extension discovery for already installed local surfaces
- tool, playbook, object, and artifact host interfaces that are promoted into stable Local Core contracts
- policy, dispatch, and executor gates that decide whether a requested action can run
- local routing and registry surfaces that keep the host aware of installed capabilities

Capability-owned material includes:

- per-capability backend service code
- per-capability frontend UI implementation
- provider-specific schemas, payloads, adapters, and credentials
- capability-specific playbook specs and prompt material
- capability-specific storage models and migrations
- capability-specific business rules, validation rules, and execution details

Public Local Core documentation may describe the host interface, but it must not present capability-owned implementation details as Local Core architecture.

## Repository Guardrails

The repository guardrails reinforce this boundary.

The Git ignore rules exclude local data, generated artifacts, credentials, runtime bundles, installed capability directories, installed playbook directories, capability-installed model directories, and internal material.

The Docker build ignore rules exclude capability installation locations, cloud playbook locations, provider and sync service mirrors, internal material, local data, logs, environment files, and temporary files from the local image context.

The CI guardrails protect capability boundaries, cloud component leakage, cloud function leakage, route conflicts, manifest validity, import path validity, router prefix validity, and root-level script boundaries.

Anything blocked by these guardrails is not eligible for public Local Core documentation by default. It must remain internal unless it is deliberately promoted into a stable Local Core contract and no longer depends on ignored or CI-protected implementation material.

## Documentation Rule

Public Local Core docs may document:

- capability hosting contracts
- runtime shell behavior
- stable host registry, object, tool, and playbook interfaces
- dispatch and policy boundaries
- host-level activation state and guardrail behavior

Public Local Core docs must not document:

- individual capability service implementations
- ignored runtime artifacts or generated bundles
- ignored local data, uploads, logs, backups, or environment files
- internal reports, work plans, debug notes, implementation histories, and testing logs
- provider-native credentials, request payloads, or private account setup
- cloud-specific business features as if they were Local Core ownership
- capability-specific UI, playbook, schema, migration, or storage internals

If a candidate public page depends on ignored, Docker-ignored, or CI-protected paths, the page stays withheld. The public version can only describe the stable host boundary that is already represented by Local Core contracts.

## Public Boundary

Local Core owns capability hosting boundaries, not capability internals.

This means Local Core can document how installed capabilities are discovered, surfaced, gated, and invoked through stable host contracts. It must not document the inside of each capability as part of the Local Core public architecture.

The safe default is to withhold. A capability detail is only public when it has been promoted into a stable Local Core contract and verified against the current repository.
