# Meeting Attachment And Materialization

## Purpose

Define how meetings consume addressable objects and how meeting results flow
back into owner-pack artifacts, previews, proposals, and canonical state.

## Product Statement

The meeting system should be able to treat selected pack-owned entities as
portable, bounded inputs.

That means a meeting should not need:

- pack-specific prompt glue for every new scenario
- raw owner payloads
- ad hoc UI-to-playbook bindings

It should receive typed object attachments, reason over them, and then hand the
result back to pack-owned materializers.

## Core Principle

Meetings should consume object references plus bounded projections.

They should not require pack-specific prompt glue for every scenario.

## Runtime Boundary

Local-Core owns:

- attach API
- attachment envelope validation
- meeting runtime invocation
- audit trail for what objects entered a meeting

Owner packs own:

- meeting projection payload construction
- allowed verbs for their object kinds
- materialization backends
- proposal, staging, and canonical promotion semantics

## Meeting Attachment Model

A meeting attachment should contain:

- `object_ref`
- `object_summary`
- `selected_relations`
- `owner_pack`
- `meeting_projection`
- optional `governance_hints`

## Attachment Envelope

Suggested P0 attachment payload:

```json
{
  "attachment_id": "att_20260423_001",
  "meeting_id": "mtg_7788",
  "verb": "expand",
  "object_ref": {
    "uri": "mindscape://ig/reference/ref_abc123",
    "owner_pack": "ig",
    "object_kind": "reference",
    "object_id": "ref_abc123",
    "workspace_id": "ws_demo"
  },
  "object_summary": {
    "title": "IG reference ref_abc123",
    "summary_text": "Warm interior lifestyle reference with close-up opportunity."
  },
  "selected_relations": [
    {
      "relation_kind": "references",
      "to_ref": {
        "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": "scene_opening_01"
      }
    }
  ],
  "owner_pack": "ig",
  "meeting_projection": {
    "projection_type": "reference_meeting_projection",
    "payload": {}
  },
  "governance_hints": {
    "write_mode": "proposal_only"
  }
}
```

Required P0 fields:

- `verb`
- `object_ref`
- `owner_pack`
- `meeting_projection`

Recommended fields:

- `object_summary`
- `selected_relations`
- `governance_hints`

## Why Projection Matters

The meeting runtime rarely needs the full owner payload.

It usually needs:

- a compact summary
- a few related objects
- a stable identity for follow-up actions
- a bounded projection prepared by the owner pack

Projection exists to keep the meeting layer:

- portable across packs
- cheap to reason over
- auditable
- independent from owner-pack internal representation changes

## Projection Levels

Recommended levels:

### Summary projection

Used for:

- contextual UI
- quick attach flows
- basic meeting context

### Meeting projection

Used for:

- meeting reasoning
- bounded related-object expansion
- materialization routing decisions

### Materialization-ready projection

Used only when needed for a downstream materializer that requires structured
pack-owned context beyond summary data.

P0 recommendation:

- support summary projection and meeting projection
- defer specialized materialization-ready projections unless first-wave packs need them

## Materialization Outcomes

Meeting results should resolve into one of these paths:

- proposal artifact
- preview run
- handoff object
- canonical writeback
- no-write recommendation

## Result Routing Model

A meeting result should not write directly into owner state by default.

It should route through one of these modes:

### `proposal_only`

Result becomes:

- reviewable proposal artifact
- no canonical mutation yet

### `staged`

Result becomes:

- staged patch
- preview configuration
- temporary bundle or handoff for later review

### `canonical_with_review`

Result may promote into canonical owner state, but only through the owner pack's
review or promotion path.

### `recommendation_only`

Result remains:

- non-writing advice
- related object recommendations
- next-step suggestions

## Generic Verbs

The first reusable verbs should be:

- `attach`
- `recommend`
- `expand`
- `preview`
- `stage`
- `review`
- `promote`

Verb semantics:

- `attach`: add the object into meeting context
- `recommend`: ask the meeting to return related objects or pathways
- `expand`: derive a richer plan or storyboard or scene proposal from the object
- `preview`: produce a renderable or evaluable candidate
- `stage`: create a temporary artifact or patch
- `review`: send result into a review lane
- `promote`: advance an already-reviewed result toward canonical state

Wave 1 interoperability deepening should add a runtime-owned
`POST /api/v1/workspaces/{workspace_id}/object-materialize` surface for verbs
such as `review` and `promote`.

That runtime route must:

- stay generic at the transport layer
- delegate owner-specific logic to declared materializers
- return bounded review plans, staged refs, or owner routes
- avoid direct canonical mutation in runtime-owned code

## Targeting Model

Meetings often need more than one object.

Recommended attachment roles:

- `source`
- `target`
- `baseline`
- `constraint`
- `evidence`

Example:

- `ig.reference` as `source`
- `performance_direction.storyboard_scene` as `target`
- `public_persona_studio.brand_preset` as `baseline`

## Example

Input:

- `ig.reference`
- `pd.storyboard_scene`
- `pps.brand_preset`

Meeting request:

- expand the scene into a 5-10 second beat with the selected reference and brand baseline

Possible materialized outputs:

- PD proposal artifact for editorial review
- storyboard preview run metadata
- staged scene patch for later promotion

Another example:

Input:

- `multi_media_studio.generated_scene`
- `ig.reference`

Meeting request:

- recommend style references for this selected generated scene and return the
  strongest result to PD review

Possible materialized outputs:

- recommendation-only object set
- PD proposal artifact
- preview metadata tied back to the selected MMS scene

## Suggested Runtime APIs

Illustrative endpoint names:

### Attach object to meeting

P0 endpoint:

`POST /api/v1/workspaces/{workspace_id}/object-meeting-attach`

Input:

- attachment envelope

Output:

- accepted attachment summary
- meeting identity
- allowed follow-up verbs

### Materialize meeting result

Follow-on endpoint, not required for P0:

`POST /api/v1/workspaces/{workspace_id}/object-materialize`

Input:

- meeting result
- target `ObjectRef`
- requested verb

Output:

- materialization outcome
- created artifact refs
- review or promotion requirements

## Materializer Contract

Every materializer should define:

- accepted object kinds
- accepted verbs
- write mode
- output families
- audit metadata

Suggested result shape:

```json
{
  "success": true,
  "write_mode": "proposal_only",
  "output_type": "proposal_artifact",
  "created_refs": [
    {
      "uri": "mindscape://performance_direction/proposal_artifact/art_987"
    }
  ],
  "requires_review": true
}
```

## Governance And Audit

Every attachment and materialization step should be auditable.

Recommended audit fields:

- `meeting_id`
- `attachment_id`
- `object_ref`
- `verb`
- `target_ref`
- `write_mode`
- `created_refs`
- `promotion_required`

P0 rule:

- all canonical mutations must be attributable to a specific meeting result and materializer call

## Boundaries

- meetings do not become the source of truth for owner-pack state
- materializers remain pack-owned
- canonical writeback must remain explicit and auditable
- Local-Core does not define pack-specific review semantics
- pack internal payloads should not be copied into the shared runtime by default

## P0 Scenarios

### Scenario 1: IG ref to PD scene expansion

Flow:

1. attach `ig.reference` as `source`
2. attach `pd.storyboard_scene` as `target`
3. meeting runs `expand`
4. PD materializer returns proposal or staged storyboard mutation

### Scenario 2: MMS scene to PD review return

Flow:

1. attach `multi_media_studio.generated_scene` as `source`
2. optional related `ig.reference` set is recommended
3. meeting runs `review` or `stage`
4. PD materializer creates proposal artifact

### Scenario 3: PPS handoff as baseline injection

Flow:

1. attach `public_persona_studio.handoff` or `brand_preset`
2. meeting uses it as baseline or constraint
3. downstream materializer writes proposal or preview configuration

## Failure Handling

Recommended failure categories:

- `projection_unavailable`
- `verb_not_supported`
- `materializer_not_declared`
- `review_required_but_missing`
- `canonical_write_disallowed`
- `target_relation_invalid`

P0 behavior:

- failure to materialize should not discard the meeting result
- recommendation-only fallback should remain possible when writes fail

## Verification

### Automated

- attachment envelope validation tests
- meeting projection schema tests where declared
- materializer contract tests

### Scenario-based

- IG reference plus PD scene yields proposal or staged output
- MMS scene review flow yields PD proposal output

### Manual

- inspect audit trail for attachment and materialization
- verify canonical state is unchanged until review or promotion path is invoked

## Follow-On Specs

- meeting projection format
- generic attachment API
- proposal lane and review promotion API
