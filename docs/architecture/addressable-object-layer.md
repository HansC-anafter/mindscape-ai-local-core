# Addressable Object Layer

The Addressable Object Layer is the Local Core host contract that turns owner-managed entities into stable object references that can be selected, searched, attached to meetings, acted on, materialized, and projected as bounded graph context.

This page describes the released public architecture scope for the current repository.

## Runtime Identity

AOL uses `ObjectRef` as the stable transport identity for an addressable object. An object reference carries enough owner, kind, identity, workspace, version, selector, and source metadata for Local Core to route host-level object operations.

Selectors describe the user-facing target behind an object reference. Public documentation should treat selector support as typed bounded targeting, not as an exhaustive list of owner-specific selector payloads.

Object identity is transport-level identity. Owner systems still own their canonical schemas, storage, business rules, and object-specific resolver behavior.

## Object Catalog

Installed object providers can declare object exports. Local Core normalizes those declarations into a runtime object catalog that summarizes host-visible identity, display, search, selection, meeting, action, materialization, and graph support.

The catalog is a local runtime read model over installed object providers. It is not a public authoring guide for provider internals and it does not transfer ownership of provider state to Local Core.

## Object Index and Mentions

Local Core maintains workspace-scoped object instance records for concrete addressable objects. Records carry bounded summaries, search and mention metadata, affordance hints, and freshness metadata for host surfaces.

Object instance indexing updates the local object instance registry from owner-managed sources. Public documentation should describe the read model and search behavior, not the private indexing schedule or backend invocation details.

The same read model backs object search and mention completion for workspace surfaces.

## Selection and Host Shell

The web console exposes an AOL runtime shell for object-aware pages. A supported surface can expose an object selection anchor and ask Local Core to resolve a selected target into one or more addressable objects.

Selection resolution returns a status of resolved, ambiguous, or unresolved. A resolved object includes an `ObjectRef`, bounded summary, and contextual actions such as attach-to-meeting or opening the owner surface when supported.

Ambiguous selections remain bounded: the host shell can present candidates, but the selected object still has to resolve to a stable object reference before meeting attachment or action invocation.

## Meeting Attachment

AOL can attach selected objects into meeting sessions with explicit role-bearing context.

Meeting attachment builds bounded context entries instead of copying raw owner-managed state. Meeting surfaces and downstream runtime paths can refer to selected objects through stable references.

Attachment may feed review and materialization workflows when the selected object kind declares compatible support, but the owner system remains responsible for object-specific state changes.

## Object Actions and Materialization

Object actions are provider-declared affordances coordinated by Local Core. The runtime can plan, invoke, and close actions while keeping provenance and object relations bounded to the local read model.

Materialization is owner-managed. Local Core coordinates host request context and error handling, while the owner system remains responsible for deciding whether a requested materialization is valid and what state it changes.

## Graph Projection

AOL supports bounded object graph projection for selected objects. Projection can come from an owner graph backend when declared or from Local Core relation read models.

Graph projections provide bounded object summaries and relation context for inspection. They are not unrestricted graph database access.

## Public Boundary

Local Core owns object identity transport, object catalog normalization, workspace object instance and relation read models, object search and mention completion, selection resolution, host-shell coordination, meeting attachment, object action orchestration, materialization coordination, and bounded graph projection.

Local Core does not publicly own:

- capability canonical object schemas
- capability business rules or storage internals
- unrestricted raw owner-owned state export
- provider-native runtime payloads
- private rollout plans or validation material
- capability authoring tutorials

Public AOL documentation should describe the stable local runtime contract and ownership boundary. Unreleased API references, rollout history, private validation captures, and implementation plans remain withheld until they are rewritten as stable public contracts.
