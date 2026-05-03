# Governance Context and Lens

Mindscape AI Local Core routes execution through local governance context instead of treating user requests as raw prompt dispatch. Governance context combines policy, memory selection, lens state, runtime constraints, evidence, and review surfaces.

This page describes the released public architecture scope for the current repository.

## Governance Context

The governance context read model compiles workspace state into a structured packet for execution. It can include bounded context from:

- workspace, project, profile, mode, and execution scope
- effective lens metadata and lens-derived context
- runtime, sandbox, governance, and memory policy
- governed memory and goal context
- optional schedule or meeting metadata

The output is split into a governance context block and a selected memory packet. This keeps policy and memory selection visible as execution input, not hidden inside private assembly layers.

## Policy and Preflight

Local Core includes governance services for:

- policy checks across roles, data domains, PII handling, and cross-project access
- cost governance and usage quota monitoring
- node governance for execution graph decisions
- playbook preflight checks
- agent preflight checks for risky task descriptions, high-risk skills, sandbox boundaries, and resource limits
- governance decision recording

These services are local policy and review surfaces. They should not be documented as an external account policy system.

## Workspace Governance Surfaces

Workspace governance surfaces support governance decisions, cost monitoring, governance metrics, canonical memory review, memory health, and memory impact graph views.

These surfaces support inspection and lifecycle transitions for governed local state. They are not generic write APIs for arbitrary policy mutation.

## Mind-Lens

Mind-Lens is the interpretation and viewpoint layer used by Local Core. It is represented by local graph state, effective lens resolution, override layers, execution evidence, and review surfaces.

Lens surfaces are local execution-context surfaces, but this page is not an endpoint reference.

Current lens behavior includes:

- graph-backed lens state and workspace binding
- effective lens resolution across profile, workspace, and session layers
- execution evidence and receipt surfaces
- review and packaging support as host-managed lens operations

## Execution Context Injection

Meeting orchestration resolves an effective lens for execution context injection and stores lens hash metadata where available. Dispatch can also carry lens context into per-phase agent execution. Memory writeback can attach lens receipts and lens patches as evidence.

Lens state should be described as user-controlled execution context. It is not a provider-native template dump and it is not a replacement for policy checks.

## Public Boundary

Local Core owns local governance context compilation, policy checks, preflight checks, governance decision records, workspace governance review surfaces, and Mind-Lens resolution.

Local Core does not publicly own:

- external account policy administration
- provider-native policy payloads
- private execution templates as public contracts
- unrestricted mutation of governed memory
- installed capability internals that only consume governance context

Public governance documentation should describe the local governance boundary, evidence surfaces, and execution context boundaries. It should not publish internal policy migration notes, private risk tables, or unreleased provider-specific schemas.
