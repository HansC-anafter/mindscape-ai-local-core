# Selection And Contextual Action Runtime

## Purpose

Define how Local-Core turns a user selection into an object-aware runtime action
without hard-coding pack-to-pack UI bindings.

## Product Reframe

This architecture is not primarily just a "global toolbar buttons" feature.

It is a runtime capability where:

- the user selects something meaningful
- the runtime resolves that selection into one or more addressable objects
- the runtime presents contextually valid actions
- the runtime launches meeting, preview, review, or owner-surface flows using
  stable object identities

The toolbar or popover is only one projection surface for that capability.
For this rollout, however, any claim that AOL is `global` or `全站可用`
requires one Local-Core-owned always-visible global entry anchor in the shared
workspace shell.

## Reframe The Problem

The platform should not start from per-pack button matrices or from detached
toolbar chrome alone.

It should start from:

1. user selects a meaningful thing
2. runtime resolves it into one or more `ObjectRef`s
3. runtime shows contextual actions based on object type and relations
4. runtime launches meeting, preview, proposal, or canonical surface

When the runtime is exposed as a global user-facing tool, that runtime may
project through one shared Local-Core-owned global anchor. The anchor is not
the architecture itself; it is the approved projection surface for entering the
selection-driven runtime flow.

## Runtime Ownership

This runtime remains Local-Core owned.

Local-Core owns:

- selection state
- one shared global entry anchor when AOL is exposed as a global lane
- selection-to-object resolution entry
- object summary popover
- contextual action surface
- canonical meeting launch semantics
- execution and trace identity for launched flows

Packs own:

- selection hints exposed by their installed UI
- object resolvers
- owner-surface URLs
- materialization backends

Packs do not own the generic launch shell.

## Design Principles

### 1. Selection first, dispatch second

The runtime must resolve what was selected before choosing which playbook,
meeting, or owner action to invoke.

### 2. The runtime accepts partial information

Not every surface can expose a full `ObjectRef` directly.

The runtime should accept partial hints and then normalize them through pack-owned resolvers.

### 3. Contextual actions are object-driven

Actions are derived from object kind, relations, and meeting/materializer
availability, not hard-coded per-screen button matrices.

### 4. The same object can be invoked from multiple surfaces

Examples:

- an IG reference tile
- a PD storyboard chip
- an MMS focus panel
- a review lane row

These all resolve into stable `ObjectRef` identities even if the visual surface differs.

## Selection Sources

Recommended source families:

### Explicit object selection

The surface already knows the object identity.

Examples:

- clicking an IG reference card
- selecting a storyboard scene row
- clicking an MMS generated scene thumbnail

### Contextual surface selection

The surface knows partial metadata but not the final object identity.

Examples:

- selecting a DOM element with `data-*` object hints
- selecting a row that only exposes `scene_id` and `session_id`

### Synthetic invocation

The runtime is invoked from search, keyboard command, or scripted handoff,
without a visible selected element.

Examples:

- command palette
- "bring `ref_abc123` into meeting"
- meeting follow-up from prior object refs

## Selection Payload Contract

Recommended runtime selection envelope:

```json
{
  "selection_id": "sel_20260423_001",
  "workspace_id": "ws_demo",
  "surface": {
    "surface_type": "installed_pack_ui",
    "pack_code": "ig",
    "surface_id": "ig.references_grid",
    "route": "/workspaces/ws_demo/capabilities/ig"
  },
  "element": {
    "element_id": "ref-card-abc123",
    "label": "Reference Card",
    "bounds": {"x": 812, "y": 224, "w": 216, "h": 216}
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

Suggested fields:

- `selection_id`
- `workspace_id`
- `surface`
- `element`
- `hints`
- `mode`

P0 rule:

- `bounds` and host-level pointer data are optional
- `hints` may contain a complete object ref or only partial information

## Selection Modes

Recommended initial modes:

- `resolve_only`
- `contextual_actions`
- `attach_to_meeting`
- `open_owner_surface`

P0 should prioritize:

- `contextual_actions`
- `attach_to_meeting`

## Selection Pipeline

Planned stages:

1. `surface_capture`
   - current surface metadata
   - selected element metadata when available
   - optional pointer or hover anchor
2. `object_resolution`
   - pack-aware resolver maps the selection to `ObjectRef`
3. `summary_expansion`
   - runtime fetches summary and relations
4. `action_surfacing`
   - runtime offers meeting actions and owner-pack actions
5. `launch`
   - runtime opens a meeting or canonical execution surface with stable IDs

## Resolution Strategy

### Direct resolution

If the selection payload already carries a complete object hint, the runtime
constructs `ObjectRef` immediately.

### Hint-assisted resolution

If the selection only contains partial hints, the runtime calls the owner-pack
resolver to disambiguate.

### Multi-candidate resolution

If one selection could map to multiple objects, the runtime should:

1. return candidate summaries
2. ask the user to confirm in the contextual surface
3. proceed only after disambiguation

P0 recommendation:

- allow at most one confirmation step
- do not auto-launch a meeting when resolution is ambiguous

## Contextual Action Model

Actions should be grouped into four families:

### Meeting actions

- attach to meeting
- expand in meeting
- recommend related objects

### Review and staging actions

- preview and stage
- send to proposal lane
- promote after review

### Navigation actions

- open owner surface
- open canonical execution or review surface

### Utility actions

- copy object ref
- inspect summary
- inspect lineage

## Minimal P0 Actions

- `attach_to_meeting`
- `recommend_related_objects`
- `preview_and_stage`
- `open_owner_surface`

Suggested P0 mapping:

| Object kind | Contextual actions |
|---|---|
| `ig.reference` | `attach_to_meeting`, `recommend_related_objects`, `open_owner_surface` |
| `performance_direction.storyboard_scene` | `attach_to_meeting`, `preview_and_stage`, `open_owner_surface` |
| `multi_media_studio.generated_scene` | `attach_to_meeting`, `preview_and_stage`, `open_owner_surface` |

## Example Runtime Flow

An IG reference tile is selected:

1. selection resolves to `mindscape://ig/reference/ref_xxx`
2. runtime requests summary and related objects
3. runtime shows actions such as:
   - bring into meeting
   - use in storyboard expansion
   - recommend similar refs
   - open IG detail

An MMS generated scene is selected:

1. selection resolves to `mindscape://multi_media_studio/generated_scene/run_x.scene_03`
2. runtime requests summary and owner-pack relation hints
3. runtime shows actions such as:
   - return to PD review lane
   - recommend style refs
   - attach to meeting with current storyboard context
   - open MMS run detail

## Suggested Runtime Endpoints

Names are illustrative and should align with existing Local-Core route style.

### Resolve selection

`POST /api/v1/workspaces/{workspace_id}/selection/resolve`

Input:

- selection envelope

Output:

- resolved `ObjectRef`
- candidate summaries if ambiguous
- contextual actions if requested

### Get contextual actions

`POST /api/v1/workspaces/{workspace_id}/contextual-actions`

Input:

- `ObjectRef`
- optional current meeting or execution context

Output:

- action list
- lightweight object summary
- relation hints for display

### Launch meeting attach

`POST /api/v1/workspaces/{workspace_id}/object-meeting-attach`

Input:

- one or more resolved `ObjectRef` payloads
- verb
- optional target object refs
- optional intent summary and write mode

Output:

- meeting attachment summary
- optional staged or reviewable output refs

## Surface Integration Contract

Installed pack UI should be able to expose selection hints through a small integration surface.

Recommended options:

- data attributes on rendered elements
- event payloads published through a runtime surface bridge
- explicit `onSelectObject(...)` callbacks in installed workbench components

P0 rule:

- any one stable mechanism is acceptable
- do not block P0 on a universal host-level overlay protocol

## State Model

Recommended runtime states:

- `idle`
- `captured`
- `resolving`
- `resolved`
- `ambiguous`
- `actionable`
- `launching`
- `failed`

This state model is useful for:

- contextual popovers
- debug panels
- telemetry and failure analysis

## Observability

Recommended events:

- `selection_captured`
- `selection_resolve_started`
- `selection_resolve_succeeded`
- `selection_resolve_ambiguous`
- `selection_resolve_failed`
- `contextual_action_invoked`
- `meeting_attach_launched`

P0 telemetry should capture:

- owner pack
- object kind
- source surface
- resolution latency
- chosen action
- failure category when applicable

## Guardrails

- do not embed pack-private launchers as the generic runtime pattern
- do not make the toolbar itself responsible for pack business logic
- do not skip object resolution and jump straight to playbook dispatch
- do not let contextual surfaces mutate canonical owner state directly
- do not require every pack UI to adopt host-level pointer capture before onboarding
- do not couple object resolution to one visual component library or DOM structure

## P0 Boundaries

P0 should support:

- explicit object selection from installed pack UIs
- contextual action popover or equivalent surface
- attach-to-meeting launch path

P0 should not require:

- OS-wide element capture
- arbitrary external window targeting
- universal drag selection
- generalized multi-select compare UI

## Verification

### Automated

- selection envelope validation
- selection-to-object resolution unit tests
- contextual action generation tests

### Scenario-based

- IG reference card resolves and offers meeting attach
- MMS generated scene resolves and offers proposal or review path

### Manual

- select an object in a first-wave pack UI
- confirm summary and actions render correctly
- launch a meeting attachment without pack-private launcher code

## Open Work

- selection capture contract across installed pack UI
- multi-object selection
- keyboard-first contextual invocation
- host-level or overlay-level element targeting
