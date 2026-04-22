# Object Model And Identity

## Purpose

Define the minimum shared object contract for cross-pack runtime behavior without
centralizing all pack-owned payloads into a single schema or database.

## Problem Statement

Today the platform already has many object-like identities:

- `reference_id`
- `artifact_id`
- `scene_asset_id`
- `handoff_id`
- `storyboard_id`
- `chapter_id`
- `demo_video_id`

They are useful inside their owner packs, but there is no single runtime-level
identity contract that lets Local-Core treat them as one interoperable object layer.

## Architectural Position

The Addressable Object Layer is:

- a transport and orchestration contract
- a projection input for graph, meetings, and contextual actions
- not a new canonical data store
- not a replacement for owner-pack schemas

This layer should be treated similarly to the runtime SDK contract lane:

- stable transport contract owned by the platform
- owner-pack payload schemas remain outside the shared kernel
- runtime projections consume the shared contract, then call pack-owned resolvers

## Design Principles

### 1. Object identity is shared, payload ownership is not

The platform shares identity and orchestration semantics.

The owner pack keeps:

- canonical payload structure
- storage layout
- business invariants
- writeback rules

### 2. Projection is cheap, truth is explicit

Toolbar popovers, graph nodes, meeting attachments, and review panels may all
project the same object differently.

None of those projections become the canonical store.

### 3. Runtime does not scan cloud source

Local-Core should only know about object kinds from installed pack metadata and
installed runtime modules.

### 4. Pack-to-pack interoperability happens through stable refs

Cross-pack flows should pass `ObjectRef` and bounded projections rather than
owner-pack internal payloads.

## Proposed Shared Contract

Minimum runtime-level types:

- `ObjectRef`
- `ObjectSummary`
- `ObjectRelation`
- `ObjectAction`
- `ObjectResolverResult`

Recommended identity shape:

- `uri`: `mindscape://{owner_pack}/{object_kind}/{object_id}`
- `owner_pack`
- `object_kind`
- `object_id`
- optional `workspace_id`
- optional `version`

### `ObjectRef`

Minimum transport identity:

```json
{
  "uri": "mindscape://ig/reference/ref_abc123",
  "owner_pack": "ig",
  "object_kind": "reference",
  "object_id": "ref_abc123",
  "workspace_id": "ws_demo",
  "version": "latest"
}
```

Required fields:

- `uri`
- `owner_pack`
- `object_kind`
- `object_id`

Optional fields:

- `workspace_id`
- `version`
- `selector`
- `source_surface`

Field intent:

- `selector`: optional pointer into a sub-part of the object, for example one
  storyboard scene inside a storyboard object
- `source_surface`: where the selection came from, for example `ig.references_grid`

### `ObjectSummary`

Bounded projection for fast UI and meeting context.

Suggested fields:

- `ref`
- `title`
- `subtitle`
- `summary_text`
- `status`
- `labels`
- `thumbnail_ref`
- `owner_surface_url`
- `capabilities`
- `updated_at`

The summary must be:

- small enough for contextual UI
- safe to cache briefly
- useful without loading pack-internal detail payloads

### `ObjectRelation`

Represents graph and meeting edges without requiring full object hydration.

Suggested fields:

- `from_ref`
- `to_ref`
- `relation_kind`
- `direction`
- `strength`
- `evidence`

Recommended `relation_kind` families:

- `derived_from`
- `references`
- `contains`
- `belongs_to`
- `staged_for`
- `reviews`
- `promotes`
- `uses_brand_baseline`
- `influences`

### `ObjectAction`

Contextual runtime action surfaced by Local-Core after resolution.

Suggested fields:

- `action_code`
- `label`
- `description`
- `verb`
- `mode`
- `requires_review`
- `target_kind`

Recommended P0 verbs:

- `attach`
- `recommend`
- `expand`
- `preview`
- `stage`
- `review`
- `promote`

### `ObjectResolverResult`

Aggregates the bounded response from a pack-owned resolver.

Suggested fields:

- `ref`
- `summary`
- `detail`
- `relations`
- `actions`
- `projections`
- `resolution_status`
- `errors`

Recommended rule:

- `detail` is optional in P0
- `summary` and `resolution_status` are mandatory when resolution succeeds

## Identity Rules

### URI grammar

Canonical URI:

`mindscape://{owner_pack}/{object_kind}/{object_id}`

Examples:

- `mindscape://ig/reference/ref_abc123`
- `mindscape://performance_direction/storyboard_scene/scene_opening_01`
- `mindscape://multi_media_studio/generated_scene/run_7788.scene_03`
- `mindscape://yogacoach/chapter/chapter_1740`

### ID stability rules

- `object_id` stability is owner-pack responsibility
- `uri` stability is the cross-pack guarantee
- display labels are never used as cross-pack identity

### Version rules

Use `version` only when the object family has meaningful revision identity.

Examples:

- `latest`
- semantic revision hash
- artifact version number

P0 rule:

- omit `version` unless the owner pack already has a stable revision model

### Selector rules

Use `selector` when the selected surface points at a sub-entity but the owner
pack still wants one canonical top-level object.

Examples:

- selected scene inside storyboard
- selected chapter inside demo video
- selected cut range inside an MMS run

## Catalog And Resolution Split

The runtime should distinguish between:

- `catalog metadata`
- `resolver output`

### Catalog metadata

Install-time, cheap, and static enough to index:

- owner pack
- object kind
- resolver availability
- meeting projection availability
- materializer verbs

### Resolver output

Runtime, object-instance-aware, possibly dynamic:

- summary
- detail
- relations
- actions
- meeting projection payload

This split prevents the object catalog from becoming a second source-of-truth database.

## Object Families

### Pack-surface objects

Examples:

- capability
- playbook
- tool
- api
- ui_component
- shared contract/schema

### Runtime-instance objects

Examples:

- ig reference
- MMS run
- MMS scene
- PD storyboard
- PD storyboard scene
- proposal artifact
- handoff
- yogacoach segment
- yogacoach chapter
- demo video

## P0 Object Ownership Map

Initial owner mapping:

| Owner pack | Object kinds |
|---|---|
| `ig` | `reference`, `source_account` |
| `performance_direction` | `storyboard`, `storyboard_scene`, `proposal_artifact`, `direction_session` |
| `multi_media_studio` | `run`, `generated_scene`, `scene_patch` |
| `public_persona_studio` | `handoff`, `brand_preset` |
| `yogacoach` | `segment`, `chapter`, `demo_video` |

This is intentionally narrow.

P0 should prove one usable interoperability lane before expanding the catalog.

## Resolution Modes

Recommended resolver modes:

- `summary_only`
- `summary_with_relations`
- `full_detail`
- `meeting_projection`

P0 runtime behavior:

- default to `summary_with_relations`
- request `meeting_projection` only when launching meeting attachment

## Suggested Runtime API Shape

These names are illustrative and should be aligned with existing Local-Core API style.

P0 authoritative endpoints are defined in:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs/api/addressable-object-layer-runtime-api.md`

Suggested runtime endpoints:

- `GET /api/v1/workspaces/{workspace_id}/object-catalog`
- `POST /api/v1/workspaces/{workspace_id}/selection/resolve`
- `POST /api/v1/workspaces/{workspace_id}/object-meeting-attach`
- follow-on: `POST /api/v1/workspaces/{workspace_id}/objects/resolve`

Suggested resolve request:

```json
{
  "ref": {
    "uri": "mindscape://ig/reference/ref_abc123",
    "owner_pack": "ig",
    "object_kind": "reference",
    "object_id": "ref_abc123",
    "workspace_id": "ws_demo"
  },
  "mode": "summary_with_relations"
}
```

## Validation Rules

### Required platform validations

- every `uri` round-trips into `owner_pack`, `object_kind`, and `object_id`
- `owner_pack` is installed before object resolution is attempted
- catalog-declared object kinds have matching resolver declarations
- meeting attachment is blocked if the object kind has no meeting projection

### Required pack validations

- stable `object_id` extraction
- safe summary projection
- no leaking of owner-private raw payloads by default
- explicit error shape when the underlying object no longer exists

## Compatibility Guidance

The Addressable Object Layer should complement, not replace:

- current pack APIs
- current artifact IDs
- current handoff models
- current shared runtime SDK contract

P0 should translate existing owner-pack identifiers into `ObjectRef`.

It should not require immediate migration of every internal pack API.

## Ownership Rules

- Local-Core owns the shared transport contract and runtime catalog/index.
- Packs own canonical payload schemas and resolver/materializer semantics.
- Runtime projections must not become the new source of truth.

## Failure Model

Resolver failures should be explicit and typed.

Suggested categories:

- `object_not_found`
- `owner_pack_not_installed`
- `resolver_not_declared`
- `projection_unavailable`
- `materializer_unavailable`
- `invalid_object_ref`

P0 rule:

- failure to resolve one object must not crash the whole contextual runtime
- the runtime should still render a user-facing explanation when a selected
  object cannot be hydrated

## Non-Goals

- building a universal payload schema for all packs
- copying all owner-pack data into one database
- forcing every pack to onboard in the first wave
- replacing existing pack-specific APIs before the object layer exists

## Follow-On Specs

- selection capture and contextual action runtime
- meeting attachment contract
- graph projection contract
- install-time object catalog synchronization
