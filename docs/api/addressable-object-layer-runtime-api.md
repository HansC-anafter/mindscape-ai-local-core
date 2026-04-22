# Addressable Object Layer Runtime API

> **Document Date**: 2026-04-23
> **Status**: Draft
> **Version**: v0.2

---

## Overview

This document defines the first runtime API surface for the Addressable Object Layer.

P0 scope is intentionally narrow but complete enough to prove one cross-pack
meeting path:

- `ObjectRef`
- object catalog listing
- selection resolve API
- meeting attach API

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
  "objects": [
    {
      "uri": "mindscape://ig/reference/ref_abc123",
      "owner_pack": "ig",
      "object_kind": "reference",
      "object_id": "ref_abc123",
      "workspace_id": "ws_demo",
      "source_surface": "ig.references_grid"
    }
  ],
  "target_ref": {
    "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
    "owner_pack": "performance_direction",
    "object_kind": "storyboard_scene",
    "object_id": "scene_opening_01",
    "workspace_id": "ws_demo"
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
| `objects` | array | yes | One or more resolved `ObjectRef` payloads to attach |
| `target_ref` | object or null | no | Optional target `ObjectRef` for attach verbs that need a destination |
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
      "uri": "mindscape://performance_direction/proposal_artifact/art_987",
      "owner_pack": "performance_direction",
      "object_kind": "proposal_artifact",
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
- Canonical owner-pack promotion must still happen through the owner-pack review
  path returned in `review_routes`.

#### Status Codes

- `200 OK` — meeting attach accepted
- `400 Bad Request` — malformed attach payload
- `401 Unauthorized` — authentication failed
- `404 Not Found` — workspace or target object not found
- `409 Conflict` — target pack or verb combination rejects the attach request
- `422 Unprocessable Entity` — valid payload but unsupported object kind, verb, or write mode

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
- The runtime must not scan cloud repo source in order to resolve catalog or selection data.
- The runtime may return `ambiguous` instead of guessing when multiple candidates are plausible.
- Pack-specific owner routes may be returned in summaries, but no canonical owner mutation may happen through this API.
- `object-meeting-attach` is part of P0. Generic `object-materialize` remains
  follow-on work until the API/spec is explicitly widened.
- P0 meeting success is satisfied by bounded attachments plus an owner-pack
  reviewable output path; it does not require a generic cross-pack canonical
  writeback route.

---

## Compatibility Notes

- Existing pack APIs remain the canonical source for rich detail and business operations.
- Existing IDs such as `reference_id`, `storyboard_id`, `artifact_id`, and `scene_id` remain valid inside owner packs.
- This API wraps those owner IDs inside `ObjectRef` without forcing immediate internal migration.

---

## Follow-On APIs

Not part of this document's P0 scope, but expected next:

- object resolve by `ObjectRef`
- object materialization API
- richer graph projection API
