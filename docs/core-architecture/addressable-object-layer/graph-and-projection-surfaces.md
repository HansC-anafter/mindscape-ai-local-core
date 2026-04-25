# Graph And Projection Surfaces

## Purpose

Clarify the role of graph, toolbar, review lanes, and workbench surfaces once
the Addressable Object Layer exists.

## Primary Rule

Graph and UI surfaces are projections.

They are not the canonical owner of object truth.

## Projection Surfaces

Examples:

- execution graph
- contextual toolbar/popover
- meeting attachment panel
- review/proposal lanes
- workbench side panels

## What They Consume

Projection surfaces should consume:

- `ObjectRef`
- summary/detail projections
- object relations
- lineage pointers
- execution and review metadata

## What They Must Not Become

- a replacement object registry
- a second owner schema
- a hidden writeback path that bypasses owner-pack materializers

## Graph-Specific Guidance

The current execution graph should evolve from a mainly execution-centric graph
into an object-aware projection layer.

That means:

- more node kinds can exist
- lineage can include refs, storyboard scenes, proposals, handoffs, and previews
- graph expansion still consumes runtime projections rather than raw owner data
- runtime graph-aware surfaces should converge on
  `POST /api/v1/workspaces/{workspace_id}/object-graph/project` as the shared
  normalization lane for owner-pack graph projections

## Asset Map Evolution

The current meeting asset map is workspace-oriented.

This architecture should evolve it toward:

- addressable object bundles
- owner-pack relations
- reusable cross-pack meeting attachments

## Follow-On Work

- object-aware node taxonomy
- projection caching rules
- graph expansion heuristics
- graph traversal and subgraph request contracts beyond bounded projection
