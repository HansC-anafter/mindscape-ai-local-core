# Addressable Object Layer

The Addressable Object Layer is the Local Core host contract that turns owner-managed entities into stable object references that can be selected, searched, attached to meetings, acted on, materialized, and projected as bounded graph context.

This page describes the released public architecture scope for the current repository.

## Runtime Identity

AOL uses `ObjectRef` as the stable transport identity for an addressable object. An object reference carries enough owner, kind, identity, workspace, version, selector, and source metadata for Local Core to route host-level object operations.

Selectors describe the user-facing target behind an object reference. Public documentation treats selector support as typed bounded targeting. Owner-specific selector payloads stay with the owner.

Object identity is transport-level identity. Owner systems still own their canonical schemas, storage, business rules, and object-specific resolver behavior.

## Object Catalog

Installed object providers can declare object exports. Local Core normalizes those declarations into a runtime object catalog that summarizes host-visible identity, display, search, selection, meeting, action, materialization, and graph support.

The catalog is a local runtime read model over installed object providers. Provider internals and provider state stay with the provider owner.

## Object Index and Mentions

Local Core maintains workspace-scoped object instance records for concrete addressable objects. Records carry bounded summaries, search and mention metadata, affordance hints, and freshness metadata for host surfaces.

Object instance indexing updates the local object instance registry from owner-managed sources. Public documentation describes the read model and search behavior. Indexing schedules and owner-specific invocation details stay with the owner.

The same read model backs object search and mention completion for workspace surfaces.

## Selection and Host Shell

The web console exposes an AOL runtime shell for object-aware pages. A supported surface can expose an object selection anchor and ask Local Core to resolve a selected target into one or more addressable objects.

Selection resolution returns a status of resolved, ambiguous, or unresolved. A resolved object includes an `ObjectRef`, bounded summary, and contextual actions such as attach-to-meeting or opening the owner surface when supported.

Ambiguous selections remain bounded: the host shell can present candidates, but the selected object still has to resolve to a stable object reference before meeting attachment or action invocation.

## Inline References and Preview

Workspace review surfaces can render object references inline. The inline reference surface reads a bounded object summary from the local object runtime and can request a targeted sync before retrying when indexing is still pending.

This keeps object references usable in human review while owner-managed object state stays with the object owner. The preview is a workspace convenience over stable object identity.

## Meeting Attachment

AOL can attach selected objects into meeting sessions with explicit role-bearing context.

Meeting attachment builds bounded context entries instead of copying raw owner-managed state. Meeting surfaces and downstream runtime paths can refer to selected objects through stable references.

Attachment may feed review and materialization workflows when the selected object kind declares compatible support, but the owner system remains responsible for object-specific state changes.

## Object Actions and Materialization

Object actions are owner-declared affordances coordinated by Local Core. The host can plan, invoke, and close actions while keeping provenance and object relations bounded to the local read model.

Materialization is owner-managed. Local Core coordinates host request context and error handling, while the owner system remains responsible for deciding whether a requested materialization is valid and what state it changes.

## Graph Projection

AOL supports bounded object graph projection for selected objects. Projection can come from an owner graph surface when declared or from Local Core relation read models.

Graph projections provide bounded object summaries and relation context for inspection.

## Public Boundary

Local Core owns object identity transport, object catalog normalization, workspace object instance and relation read models, object search and mention completion, inline object previews, selection resolution, host-shell coordination, meeting attachment, object action orchestration, materialization coordination, and bounded graph projection.

Related owners keep:

- capability-owned canonical object schemas
- capability business rules or storage internals
- unrestricted raw owner-managed state export
- adapter runtime payloads
- rollout and verification records
- capability authoring tutorials

Public AOL documentation describes the stable local runtime contract and ownership boundary. Draft API references, rollout history, validation captures, and implementation plans become public only after they are rewritten as stable public contracts.
