# Addressable Object Layer Runtime API

> **Document Date**: 2026-04-23
> **Status**: Draft
> **Version**: v0.3

---

## Overview

This document defines the first runtime API surface for the Addressable Object Layer.

The runtime API now has two layers of scope:

- P0 proof scope:
  - `ObjectRef`
  - object catalog listing
  - selection resolve API
  - meeting attach API
- Wave 1 interoperability deepening:
  - generic object materialization API for review and promote verbs
  - runtime graph projection API with normalized relation payloads

P0 does not include a generic recommendation execution endpoint.
`recommend_related_objects` is currently a contextual action hint only. The
secondary MMS proof path uses `object-meeting-attach` plus owner-pack
materialization into an existing PD review lane.

This API is runtime-hosted by `mindscape-ai-local-core`.

It does not replace:

- existing pack APIs
- existing artifact endpoints
- existing meeting endpoints

It provides the first shared runtime lane for:

- selection-driven object resolution
- object-aware contextual actions
- cross-pack meeting entry

Installation of `.mindpack` files remains a control-plane concern on
`http://localhost:8220`. The APIs in this document are workspace/runtime APIs
and remain on the runtime-serving plane, typically `http://localhost:8200`.

---

## Design Principles

- Local-Core owns the runtime API surface.
- Owner packs own canonical object payloads and resolver behavior.
- The API returns bounded projections, not full owner-pack internals by default.
- The API is additive; packs without object declarations continue to work normally.

---

## Object Model

### ObjectRef

`ObjectRef` is the minimum stable transport identity for any addressable object.

**Schema**

```json
{
  "uri": "mindscape://ig/reference/ref_abc123",
  "owner_pack": "ig",
  "object_kind": "reference",
  "object_id": "ref_abc123",
  "workspace_id": "ws_demo",
  "version": "latest",
  "selector": null,
  "source_surface": "ig.references_grid"
}
```

**Fields**

| Field | Type | Required | Description |
|---|---|---:|---|
| `uri` | string | yes | Canonical URI: `mindscape://{owner_pack}/{object_kind}/{object_id}` |
| `owner_pack` | string | yes | Pack that owns canonical truth |
| `object_kind` | string | yes | Pack-local object kind |
| `object_id` | string | yes | Owner-pack stable identifier |
| `workspace_id` | string | no | Workspace-scoped context when applicable |
| `version` | string | no | Stable revision identifier, if meaningful |
| `selector` | object or null | no | Optional pointer to a sub-entity inside the object |
| `source_surface` | string | no | Surface from which the ref was produced |

**Rules**

- `uri`, `owner_pack`, `object_kind`, and `object_id` must be mutually consistent.
- Display labels must never be used as cross-pack identity.
- `version` should be omitted unless the owner pack already has a stable revision model.

### ObjectSummary

Used in catalog entries, selection resolve responses, and contextual UI.

**Schema**

```json
{
  "ref": {
    "uri": "mindscape://ig/reference/ref_abc123",
    "owner_pack": "ig",
    "object_kind": "reference",
    "object_id": "ref_abc123"
  },
  "title": "IG reference ref_abc123",
  "subtitle": "@brand_account / shortcode_abc123",
  "summary_text": "Warm interior lifestyle reference with close-up opportunity.",
  "status": "ready",
  "labels": ["reference", "ig", "lifestyle"],
  "thumbnail_ref": "/api/v1/ig/references/ref_abc123/thumbnail",
  "owner_surface_url": "/workspaces/ws_demo/capabilities/ig",
  "updated_at": "2026-04-23T08:30:00Z"
}
```

### ObjectAction

Represents a runtime-available contextual action.

Phase 0 keeps this transport intentionally narrow. It carries semantic action
labels and verbs, but not pack-owned execution targets such as method/path.
Pack-owned `actions_backend` declarations are cataloged for future widening of
the runtime surface; Phase 0 action responses remain runtime-defined.

**Schema**

```json
{
  "action_code": "attach_to_meeting",
  "label": "Bring Into Meeting",
  "description": "Attach this object to a meeting as a source or target.",
  "verb": "attach",
  "mode": "meeting",
  "requires_review": false,
  "target_kind": null
}
```

### ObjectCatalogEntry

Represents an installed object capability, not a concrete runtime instance.

**Schema**

```json
{
  "owner_pack": "ig",
  "object_kind": "reference",
  "display_name": "IG Reference",
  "supports": ["summary", "relations", "meeting_projection"],
  "summary_fields": ["reference_id", "source_shortcode", "account_handle", "thumbnail_url"],
  "resolver_capabilities": {
    "summary": true,
    "detail": false,
    "relations": true,
    "actions": true
  },
  "materializer_capabilities": {
    "available": false,
    "verbs": []
  }
}
```

---

## API Endpoints

### 1. Get Object Catalog

**GET** `/api/v1/workspaces/{workspace_id}/object-catalog`

Returns object capabilities exposed by installed packs for the given workspace runtime.

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `owner_pack` | string | no | Filter by owner pack |
| `object_kind` | string | no | Filter by object kind |
| `supports` | string | no | Filter by declared support capability |
| `include_examples` | boolean | no | Include example object refs when available |

#### Example Request

```bash
curl -X GET "http://localhost:8200/api/v1/workspaces/ws_demo/object-catalog?owner_pack=ig" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Example Response

```json
{
  "workspace_id": "ws_demo",
  "catalog_version": "2026-04-23T09:00:00Z",
  "entries": [
    {
      "owner_pack": "ig",
      "object_kind": "reference",
      "display_name": "IG Reference",
      "supports": ["summary", "relations", "meeting_projection"],
      "summary_fields": [
        "reference_id",
        "source_shortcode",
        "account_handle",
        "thumbnail_url"
      ],
      "resolver_capabilities": {
        "summary": true,
        "detail": false,
        "relations": true,
        "actions": true
      },
      "materializer_capabilities": {
        "available": false,
        "verbs": []
      }
    }
  ]
}
```

#### Response Notes

- `entries` describe installed object kinds, not concrete runtime objects.
- `catalog_version` should change whenever object declarations are re-synchronized.
- Missing packs or non-adopting packs simply do not appear in the catalog.

#### Status Codes

- `200 OK` — catalog returned
- `401 Unauthorized` — authentication failed
- `404 Not Found` — workspace does not exist

---

### 2. Resolve Selection

**POST** `/api/v1/workspaces/{workspace_id}/selection/resolve`

Resolves a UI selection into one or more addressable object candidates.

This is the main P0 entry for contextual actions.

#### Request Body

```json
{
  "selection_id": "sel_20260423_001",
  "surface": {
    "surface_type": "installed_pack_ui",
    "pack_code": "ig",
    "surface_id": "ig.references_grid",
    "route": "/workspaces/ws_demo/capabilities/ig"
  },
  "element": {
    "element_id": "ref-card-abc123",
    "label": "Reference Card",
    "bounds": {
      "x": 812,
      "y": 224,
      "w": 216,
      "h": 216
    }
  },
  "hints": {
    "owner_pack": "ig",
    "object_kind": "reference",
    "object_id": "ref_abc123",
    "source_surface": "ig.references_grid"
  },
  "mode": "contextual_actions"
}
```

#### Request Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `selection_id` | string | yes | Client-generated selection identity |
| `surface` | object | yes | Surface metadata for the current selection |
| `element` | object | no | Selected element metadata |
| `hints` | object | no | Object hints supplied by the surface |
| `mode` | string | yes | `resolve_only`, `contextual_actions`, `attach_to_meeting`, or `open_owner_surface` |

#### Resolution Modes

| Mode | Behavior |
|---|---|
| `resolve_only` | Return resolved object candidates without action expansion |
| `contextual_actions` | Return resolved objects plus action list |
| `attach_to_meeting` | Return resolved objects plus meeting-attach-ready action set |
| `open_owner_surface` | Return best owner-surface route for the selected object |

#### Response: Resolved

```json
{
  "workspace_id": "ws_demo",
  "selection_id": "sel_20260423_001",
  "status": "resolved",
  "resolved_objects": [
    {
      "ref": {
        "uri": "mindscape://ig/reference/ref_abc123",
        "owner_pack": "ig",
        "object_kind": "reference",
        "object_id": "ref_abc123",
        "workspace_id": "ws_demo",
        "source_surface": "ig.references_grid"
      },
      "summary": {
        "ref": {
          "uri": "mindscape://ig/reference/ref_abc123",
          "owner_pack": "ig",
          "object_kind": "reference",
          "object_id": "ref_abc123"
        },
        "title": "IG reference ref_abc123",
        "subtitle": "@brand_account / shortcode_abc123",
        "summary_text": "Warm interior lifestyle reference with close-up opportunity.",
        "status": "ready",
        "labels": ["reference", "ig", "lifestyle"],
        "owner_surface_url": "/workspaces/ws_demo/capabilities/ig"
      },
      "actions": [
        {
          "action_code": "attach_to_meeting",
          "label": "Bring Into Meeting",
          "description": "Attach this object to a meeting as a source or target.",
          "verb": "attach",
          "mode": "meeting",
          "requires_review": false,
          "target_kind": null
        },
        {
          "action_code": "recommend_related_objects",
          "label": "Recommend Related Objects",
          "description": "Suggest nearby refs, storyboard targets, or review pathways.",
          "verb": "recommend",
          "mode": "contextual",
          "requires_review": false,
          "target_kind": null
        }
      ]
    }
  ],
  "candidate_objects": [],
  "errors": []
}
```

#### Response: Ambiguous

```json
{
  "workspace_id": "ws_demo",
  "selection_id": "sel_20260423_001",
  "status": "ambiguous",
  "resolved_objects": [],
  "candidate_objects": [
    {
      "ref": {
        "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": "scene_opening_01"
      },
      "summary": {
        "title": "Opening scene",
        "summary_text": "Cold open / studio close-up candidate."
      }
    },
    {
      "ref": {
        "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_02",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": "scene_opening_02"
      },
      "summary": {
        "title": "Opening alt scene",
        "summary_text": "Alternative framing for the same beat."
      }
    }
  ],
  "errors": []
}
```

#### Response: Unresolved

```json
{
  "workspace_id": "ws_demo",
  "selection_id": "sel_20260423_001",
  "status": "unresolved",
  "resolved_objects": [],
  "candidate_objects": [],
  "errors": [
    {
      "code": "object_not_found",
      "message": "No addressable object could be resolved from the supplied selection hints."
    }
  ]
}
```

#### Response Semantics

| Field | Description |
|---|---|
| `status` | `resolved`, `ambiguous`, or `unresolved` |
| `resolved_objects` | Concrete resolved objects with summaries and optional actions |
| `candidate_objects` | Disambiguation candidates when one selection maps to multiple objects |
| `errors` | Structured failure or warning payloads |

#### Status Codes

- `200 OK` — request processed; inspect `status` for semantic result
- `400 Bad Request` — malformed selection payload
- `401 Unauthorized` — authentication failed
- `404 Not Found` — workspace not found
- `422 Unprocessable Entity` — selection payload valid but unsupported mode or invalid hint combination

---

### 3. Attach Objects To Meeting

**POST** `/api/v1/workspaces/{workspace_id}/object-meeting-attach`

Converts one or more resolved `ObjectRef` payloads into bounded meeting
attachments and optionally returns staged owner-pack outputs that are ready for
existing review lanes.

This is the P0 meeting-entry route. It does not bypass owner-pack review or
promotion paths.

#### Request Body

```json
{
  "meeting_type": "direction",
  "meeting_id": null,
  "entries": [
    {
      "role": "source",
      "ref": {
        "uri": "mindscape://ig/reference/ref_abc123",
        "owner_pack": "ig",
        "object_kind": "reference",
        "object_id": "ref_abc123",
        "workspace_id": "ws_demo",
        "source_surface": "ig.references_grid"
      }
    },
    {
      "role": "baseline",
      "ref": {
        "uri": "mindscape://public_persona_studio/foundation_snapshot/fs_001",
        "owner_pack": "public_persona_studio",
        "object_kind": "foundation_snapshot",
        "object_id": "fs_001",
        "workspace_id": "ws_demo"
      }
    },
    {
      "role": "constraint",
      "ref": {
        "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
        "owner_pack": "public_persona_studio",
        "object_kind": "pd_workflow_handoff",
        "object_id": "handoff_001",
        "workspace_id": "ws_demo"
      }
    },
    {
      "role": "target",
      "ref": {
        "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": "scene_opening_01",
        "workspace_id": "ws_demo"
      }
    }
  },
  "intent_summary": "Expand this ref into a 5-10s opening beat and stage it for PD review.",
  "write_mode": "proposal_only"
}
```

#### Request Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `meeting_type` | string | yes | Meeting family such as `direction`, `review`, or `ideation` |
| `meeting_id` | string or null | no | Existing meeting/session identity when attaching into an open meeting |
| `entries` | array | yes | Role-bearing entries. Each entry contains `role` plus a resolved `ref` payload. Current runtime roles are `source`, `target`, `baseline`, `constraint`, and `evidence`. |
| `intent_summary` | string | yes | Bounded operator intent for the attach request |
| `write_mode` | string | no | `proposal_only`, `staged`, or `recommendation_only` |

#### Example Response

```json
{
  "workspace_id": "ws_demo",
  "meeting_id": "mtg_7788",
  "status": "attached",
  "attachments": [
    {
      "role": "source",
      "ref": {
        "uri": "mindscape://ig/reference/ref_abc123",
        "owner_pack": "ig",
        "object_kind": "reference",
        "object_id": "ref_abc123"
      },
      "projection_level": "meeting"
    },
    {
      "role": "baseline",
      "ref": {
        "uri": "mindscape://public_persona_studio/foundation_snapshot/fs_001",
        "owner_pack": "public_persona_studio",
        "object_kind": "foundation_snapshot",
        "object_id": "fs_001"
      },
      "projection_level": "meeting"
    }
  ],
  "target_ref": {
    "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
    "owner_pack": "performance_direction",
    "object_kind": "storyboard_scene",
    "object_id": "scene_opening_01"
  },
  "staged_refs": [
    {
      "uri": "mindscape://performance_direction/storyboard_proposal_artifact/art_987",
      "owner_pack": "performance_direction",
      "object_kind": "storyboard_proposal_artifact",
      "object_id": "art_987"
    }
  ],
  "review_routes": [
    "/api/v1/capabilities/performance_direction/sessions/pd_sess_001/storyboard/proposals/art_987/review"
  ],
  "errors": []
}
```

#### Response Notes

- `status` may be `attached`, `materialized`, or `rejected`.
- P0 success may return only `meeting_id` plus attachment metadata, or it may
  also return `staged_refs` when the selected path invokes an owner-pack
  materializer that produces a proposal-only result.
- Role-bearing attach entries are preserved through meeting attachment metadata
  and, when the owner materializer supports it, forwarded as bounded
  `context_objects` for explainable proposal staging.
- Canonical owner-pack promotion must still happen through the owner-pack review
  path returned in `review_routes`.
- For backward compatibility, legacy `objects + target_ref` payloads are still
  accepted and normalized into `entries` server-side during the transition.

#### Status Codes

- `200 OK` — meeting attach accepted
- `400 Bad Request` — malformed attach payload
- `401 Unauthorized` — authentication failed
- `404 Not Found` — workspace or target object not found
- `409 Conflict` — target pack or verb combination rejects the attach request
- `422 Unprocessable Entity` — valid payload but unsupported object kind, verb, or write mode

---

### 4. Materialize Object Outcome

**POST** `/api/v1/workspaces/{workspace_id}/object-materialize`

Routes a generic runtime verb such as `review` or `promote` through an
owner-pack-declared materializer without bypassing the owner pack's review or
promotion semantics.

This endpoint is a follow-on Wave 1 interoperability API. It widens the shared
runtime lane beyond meeting entry, but it still does not introduce direct
generic canonical writes.

#### Request Body

```json
{
  "object_ref": {
    "uri": "mindscape://performance_direction/storyboard_proposal_artifact/art_987",
    "owner_pack": "performance_direction",
    "object_kind": "storyboard_proposal_artifact",
    "object_id": "art_987",
    "workspace_id": "ws_demo"
  },
  "verb": "promote",
  "meeting_id": "mtg_review_001",
  "intent_summary": "Promote the reviewed storyboard proposal into the owner review lane.",
  "write_mode": "canonical_with_review",
  "context_entries": [
    {
      "role": "baseline",
      "ref": {
        "uri": "mindscape://public_persona_studio/foundation_snapshot/fs_001",
        "owner_pack": "public_persona_studio",
        "object_kind": "foundation_snapshot",
        "object_id": "fs_001",
        "workspace_id": "ws_demo"
      }
    },
    {
      "role": "constraint",
      "ref": {
        "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
        "owner_pack": "public_persona_studio",
        "object_kind": "pd_workflow_handoff",
        "object_id": "handoff_001",
        "workspace_id": "ws_demo"
      }
    }
  ],
  "request_context": {
    "approval_state": "approved"
  }
}
```

#### Request Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `object_ref` | object | yes | Resolved source `ObjectRef` for the requested materialization |
| `verb` | string | yes | Runtime verb such as `review`, `promote`, `stage`, or `preview` |
| `intent_summary` | string | yes | Bounded operator intent for the requested materialization |
| `meeting_id` | string or null | no | Existing meeting/session identity when the owner pack wants meeting-aware review context |
| `write_mode` | string | no | `proposal_only`, `staged`, `canonical_with_review`, or `recommendation_only` |
| `context_entries` | array | no | Additional role-bearing context entries. Each entry contains `role` plus a resolved `ref` payload. |
| `request_context` | object | no | Extra bounded execution context forwarded to the owner materializer |

#### Example Response

```json
{
  "workspace_id": "ws_demo",
  "status": "planned",
  "verb": "promote",
  "object_ref": {
    "uri": "mindscape://performance_direction/storyboard_proposal_artifact/art_987",
    "owner_pack": "performance_direction",
    "object_kind": "storyboard_proposal_artifact",
    "object_id": "art_987"
  },
  "staged_refs": [],
  "review_routes": [
    "/api/v1/capabilities/performance_direction/sessions/pd_sess_001/storyboard/proposals/art_987/review"
  ],
  "canonical_routes": [
    "/api/v1/capabilities/performance_direction/sessions/pd_sess_001/storyboard"
  ],
  "request_plan": {
    "method": "POST",
    "path": "/api/v1/capabilities/performance_direction/sessions/pd_sess_001/storyboard/proposals/art_987/promote",
    "body": {
      "approval_state": "approved"
    }
  },
  "errors": []
}
```

#### Response Notes

- `status` may be `planned`, `materialized`, or `rejected`.
- Runtime success means the owner-pack materializer accepted the request and
  returned a bounded execution or review plan. It does not imply the canonical
  owner write has already happened.
- When declared by the owner materializer, `context_entries` are forwarded as
  role-bearing `context_objects` so proposal staging can preserve
  `baseline / constraint / evidence` lineage without widening generic canonical
  write semantics.
- `canonical_routes` are informational owner routes for downstream review or
  navigation; they are not runtime-owned mutation endpoints.
- For backward compatibility, legacy `context_objects` payloads are still
  accepted and normalized into `context_entries` server-side during the
  transition.

#### Status Codes

- `200 OK` — materialization request accepted
- `400 Bad Request` — malformed materialization payload
- `401 Unauthorized` — authentication failed
- `404 Not Found` — workspace or object not found
- `409 Conflict` — owner pack rejects the requested verb or write mode
- `422 Unprocessable Entity` — valid payload but unsupported object kind, verb, or materializer

---

### 5. Project Object Graph

**POST** `/api/v1/workspaces/{workspace_id}/object-graph/project`

Returns a normalized runtime graph projection for one or more resolved objects.
Owner packs may shape their own graph payloads internally, but the runtime must
normalize them before returning them to graph-aware surfaces.

#### Request Body

```json
{
  "objects": [
    {
      "uri": "mindscape://performance_direction/storyboard_proposal_artifact/art_987",
      "owner_pack": "performance_direction",
      "object_kind": "storyboard_proposal_artifact",
      "object_id": "art_987",
      "workspace_id": "ws_demo"
    }
  ],
  "include_relations": true,
  "include_summaries": true
}
```

#### Example Response

```json
{
  "workspace_id": "ws_demo",
  "projections": [
    {
      "ref": {
        "uri": "mindscape://performance_direction/storyboard_proposal_artifact/art_987",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_proposal_artifact",
        "object_id": "art_987"
      },
      "summary": {
        "title": "Proposal art_987",
        "summary_text": "Pending storyboard proposal derived from a selected source object."
      },
      "relations": [
        {
          "relation_kind": "patches_storyboard_scene",
          "direction": "outbound",
          "target_ref": {
            "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
            "owner_pack": "performance_direction",
            "object_kind": "storyboard_scene",
            "object_id": "scene_opening_01"
          },
          "metadata": {}
        }
      ],
      "metadata": {
        "projection_source": "owner_pack_graph_projection"
      }
    }
  ],
  "errors": []
}
```

#### Response Notes

- Runtime graph projections are bounded and additive; they do not become the
  source of canonical object truth.
- Relation payloads must use normalized runtime keys even if the owner pack
  emits a different internal key set.

#### Status Codes

- `200 OK` — graph projections returned
- `400 Bad Request` — malformed graph projection payload
- `401 Unauthorized` — authentication failed
- `404 Not Found` — workspace or object not found
- `422 Unprocessable Entity` — projection requested for object kinds without a declared graph projection

---

## Error Model

Structured errors should use the following shape:

```json
{
  "code": "object_not_found",
  "message": "No addressable object could be resolved from the supplied selection hints.",
  "details": {}
}
```

### Recommended Error Codes

| Code | Meaning |
|---|---|
| `object_not_found` | No matching object could be resolved |
| `invalid_selection_payload` | Required fields missing or inconsistent |
| `owner_pack_not_installed` | Selection hints reference a pack that is not installed |
| `resolver_not_declared` | Pack exists but object resolver is not declared |
| `selection_mode_not_supported` | Requested selection mode is not supported |
| `projection_unavailable` | Object exists but requested projection is not available |
| `meeting_attach_not_supported` | Attach requested for an object kind or verb the runtime cannot project in P0 |
| `target_ref_invalid` | Target ref missing, inconsistent, or unsupported for the selected attach flow |

---

## P0 Behavioral Rules

- `selection/resolve` must be safe to call from installed pack UIs without requiring full owner payloads.
- `selection/resolve` should prefer owner-pack summary resolvers when declared,
  but Phase 0 contextual action payloads remain runtime-defined rather than
  pack-owned execution descriptors.
- The runtime must not scan cloud repo source in order to resolve catalog or selection data.
- The runtime may return `ambiguous` instead of guessing when multiple candidates are plausible.
- Pack-specific owner routes may be returned in summaries, but no canonical owner mutation may happen through this API.
- `object-meeting-attach` is part of P0.
- P0 meeting success is satisfied by bounded attachments plus an owner-pack
  reviewable output path; it does not require a generic cross-pack canonical
  writeback route.
- `object-materialize` is part of the Wave 1 interoperability-deepening
  milestone. It must remain bounded to owner-pack materializers and must not
  introduce runtime-owned canonical mutation semantics.
- `object-graph/project` is part of the Wave 1 interoperability-deepening
  milestone. It must return normalized relation payloads without turning the
  runtime graph into canonical object storage.

---

## Compatibility Notes

- Existing pack APIs remain the canonical source for rich detail and business operations.
- Existing IDs such as `reference_id`, `storyboard_id`, `artifact_id`, and `scene_id` remain valid inside owner packs.
- This API wraps those owner IDs inside `ObjectRef` without forcing immediate internal migration.

---

## Follow-On APIs

Expected next after this document's Wave 1 scope:

- object resolve by `ObjectRef`
- recommendation execution route
- graph expansion and traversal heuristics
