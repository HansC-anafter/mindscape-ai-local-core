# Addressable Object Layer

The Addressable Object Layer is the Local Core runtime that turns capability-owned entities into stable objects that can be selected, searched, attached to meetings, acted on, materialized, and projected as bounded graph context.

This page describes the released public architecture scope for the current repository.

## Runtime Identity

AOL uses `ObjectRef` as the stable transport identity for an addressable object. An object reference carries the object URI, owner identifier, object kind, object ID, optional workspace, version, selector, and source surface.

Selectors describe the user-facing target behind an object reference. The current runtime recognizes selector families for object roots, DOM anchors, image regions, media time ranges, storyboard scenes and slots, timeline clips, owner-local paths, and graph nodes.

Object identity is transport-level identity. Owner capabilities still own their canonical schemas, storage, business rules, and object-specific resolver behavior.

## Object Catalog

Installed capabilities can declare object exports. Local Core normalizes those declarations into a runtime object catalog with:

- owner identifier and object kind
- display name, canonical schema, ID field, summary fields, and supported behaviors
- selector families and mention fields
- optional instance indexer backend
- resolver, meeting projection, materializer, and graph projection capability summaries
- schema-backed affordances for object actions

The catalog is a local runtime read model over installed capabilities. It is not a public authoring guide for installed capabilities and it does not transfer ownership of installed capability state to Local Core.

## Object Index and Mentions

Local Core maintains workspace-scoped object instance records for concrete addressable objects. Records include the object reference, display summary, labels, thumbnail reference, owner surface URL, mention tokens, searchable text, affordance verbs, staleness, and metadata.

Object instance indexing can be triggered through workspace routes and through the post-ready background sync loop. The sync loop discovers catalog entries with indexer backends, invokes the owner capability indexer, and stores normalized workspace records in the local object instance registry.

The same read model backs object search and mention completion for workspace surfaces.

## Selection and Host Shell

The web console exposes an AOL runtime shell for capability pages. A supported page can register a surface, expose an object selection anchor, and ask Local Core to resolve a selected target into one or more addressable objects.

Selection resolution returns a status of resolved, ambiguous, or unresolved. A resolved object includes an `ObjectRef`, bounded summary, and contextual actions such as attach-to-meeting or opening the owner surface when supported.

Ambiguous selections remain bounded: the host shell can present candidates, but the selected object still has to resolve to a stable object reference before meeting attachment or action invocation.

## Meeting Attachment

AOL can attach selected objects into meeting sessions with explicit roles such as source, target, baseline, constraint, evidence, output, meeting, session, or node.

Meeting attachment builds bounded context entries instead of copying raw owner-owned state. The meeting session metadata can carry the AOL attachment payload so downstream meeting panels, guidance flows, graph inspectors, and materializers can refer to selected objects through stable references.

Attachment can remain proposal-only, stage review routes, or materialize through an owner capability backend when the selected object kind declares compatible materializer support.

## Object Actions and Materialization

Object actions are schema-backed affordances declared by installed capabilities and coordinated by Local Core. The runtime can:

- plan an action over role-bearing object entries
- persist planning relations for provenance
- invoke the planned action through the local execution path
- close the action by indexing output objects and durable relation records

Materialization is capability-owned. Local Core coordinates request shape, role-bearing context, write mode, review routes, staged references, canonical routes, and error handling. The owner capability remains responsible for deciding whether a requested materialization is valid and what state it changes.

## Graph Projection

AOL supports bounded object graph projection for selected objects. Projection can come from an owner capability graph backend when declared. Local Core also falls back to persisted object relation records so prior action plans, action closures, and relation index writes can appear in the meeting graph inspector.

Graph projections contain object summaries, node kind metadata, normalized relation kinds, relation direction, and target object references. They are inspection context, not unrestricted graph database access.

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
