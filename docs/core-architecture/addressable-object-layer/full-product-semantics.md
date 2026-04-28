# Addressable Object Layer Full Product Semantics

Date: 2026-04-29
Status: Implementation handoff

This document is the docs-tree handoff for the full AOL product-semantics push.
The long evidence report and working implementation plan remain in
`docs-internal/implementation/2026-04-23/addressable-object-layer/`, but this
file is the intended version-control-visible source for implementation gates.

## Target

Advance AOL from coarse object transport into a product layer where first-wave
creative pack objects are:

- addressable by stable `ObjectRef`
- selectable by typed selector
- searchable and mentionable from a workspace-local index
- callable through schema-backed affordances
- visible in meeting execution graph proof with command, run, artifact, and
  provenance nodes

The delivery target is AOL-3/AOL-4 for first-wave internal packs. Federated
external adapters remain AOL-5 and are not a blocker for this phase.

## Maturity Gates

- AOL-0: ObjectRef transport, catalog declaration, hint-based selection.
- AOL-1: shared host lane and coarse object meeting attach.
- AOL-2: registry-backed object search/read/mention and typed selectors.
- AOL-3: fine-grained first-wave creative object projection.
- AOL-4: schema-backed object affordance invocation and meeting graph proof.
- AOL-5: federated external object adapters.

No rollout doc should claim "global AOL" or "everything addressable" before the
AOL-3/AOL-4 gates pass for the first-wave packs in scope.

## Execution Code Names

- `AOL-3A: Typed Selector And Instance Registry` - completed baseline for
  typed selectors, concrete object registry, search/read/complete, and sync.
- `AOL-3B: Registry-Backed Mention And Pack Coverage` - completed baseline for
  command-bar object completion plus first-wave object export expansion.
- `AOL-3C: Action Closure Registry` - completed baseline for
  `/object-actions/plan`, `/object-actions/close`, generated output object
  indexing, and closure relation indexing.
- `AOL-3D: Execution Closure Wiring` - completed baseline. Meeting/tool
  execution carries the `object_action_plan` through dispatch and closes it
  automatically when the runtime emits addressable output records.
- `AOL-3E: Meeting Execution Graph Proof` - completed baseline. Meeting graph
  reads task/object-action closure evidence from the control API and renders
  command, run, closure, output object, and degraded proof nodes.
- `AOL-3F: Command Mention Closure` - completed baseline. Meeting command bar
  resolves picker-backed and manually typed AOL tokens into structured
  `meeting_mentions`, storyboard targets, character refs, pack routes, and
  object-action planning entries.
- `AOL-3Z: Runtime Closure Gate` - completed live closure baseline. A real
  meeting command is not considered closed until the graph can show command,
  source, target, character, run, output artifact/object, and provenance
  relations from the same object-action plan. Current baseline supports both:
  task-backed `/object-actions/invoke` execution with persisted
  `object_action_closure`, and relation-only recovery when older task rows are
  missing or stale.

## First-Wave Scope

- Local-Core runtime models and APIs:
  - typed selectors
  - object instance registry
  - object read/search/resolve/sync/complete APIs
  - object action plan/invoke APIs
  - meeting-owned semantic execution graph API
- Cloud pack source contracts:
  - `ig`
  - `performance_direction`
  - `character_training`
  - `production_design`
  - `multi_media_studio`
- Shared schema/validation:
  - Local-Core `schemas/manifest.schema.yaml`
  - Local-Core `scripts/ci/validate_manifest.py`
  - Cloud `capabilities/manifest.schema.yaml`
  - Cloud `scripts/validate_manifest.py`

## Non-Negotiable Constraints

- Cloud pack source remains the source of truth for pack contracts and business
  logic. Local-Core indexes and delegates; it does not own canonical pack data.
- Object instance registry must be a durable workspace-scoped read model. A file
  cache may exist only for development fallback.
- `mindscape://...` object URIs must not be encoded into fragile path segments;
  object read should accept a JSON body or safe query parameter.
- Mention completion must use local index data on the keystroke path. It must not
  synchronously call pack indexers or owner APIs while the user is typing.
- Meeting graph primary flow must not render raw governance action items as an
  endless horizontal chain. Raw events belong in Trace mode.
- Missing graph join identifiers must produce degraded nodes with explanation,
  not silent dropped evidence.

## Acceptance Gates

1. Static architecture gate:
   `rg -n "AOL-0|AOL-1|AOL-2|AOL-3|AOL-4|AOL-5" docs/core-architecture docs-internal/implementation/2026-04-23/addressable-object-layer`

2. Manifest schema parity gate:
   `rg -n "selector_families|indexer_backend|mention_fields|affordances" schemas/manifest.schema.yaml /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/manifest.schema.yaml`

3. Manifest validation gate:
   `pytest backend/tests/aol_manifest_schema_validation_test.py backend/tests/object_catalog_registry_aol_contracts_test.py`

4. Object registry gate:
   `/object-catalog` returns declarations while `/objects/search` returns
   concrete workspace object instances. The implemented search API is
   `GET /api/v1/workspaces/<workspace_id>/objects/search?query=<text>` and
   returns concrete records in `.results`.

5. Mention UX gate:
   typing `@` in the meeting command bar shows active object/session/node
   suggestions immediately and registry-backed suggestions asynchronously.
   Manually typed AOL tokens such as `@storyboard:...`,
   `@storyboard_scene:...`, `@storyboard_proposal:...`, `@character:...`,
   `@character_card:...`, and `@pack:...` must still resolve into structured
   meeting references even when the picker data is stale or incomplete.

6. Object action planning gate:
   a command with source reference, target storyboard, and character reference
   returns a structured plan before dispatch, then `/object-actions/invoke`
   persists a task row and closes addressable outputs through the object
   registry.

7. Meeting graph proof gate:
   completed tasks show command, source object, target, character, run,
   artifact/output, and provenance edges.

8. Relation-only recovery gate:
   if object-action relation records exist for a meeting but the task row is
   absent or stale, the graph must still render a command node, run-proof node,
   object endpoints, and relation/provenance edges from the relation metadata.

## Evidence

The evidence base is:

- `docs-internal/implementation/2026-04-23/addressable-object-layer/addressable-object-layer-full-product-semantics-evidence-report-2026-04-28.md`
- `docs-internal/implementation/2026-04-23/addressable-object-layer/addressable-object-layer-full-product-semantics-implementation-plan-2026-04-28.md`

## Quality Review Note

Last reviewed: 2026-04-29.

The AOL-3Z runtime closure path has passing targeted backend and frontend tests,
and its P0 closure gate was re-verified against the local runtime through Docker
internal networking. The performance-direction executor closure now lives in the
cloud pack source of truth and is deployed through a `.mindpack` install rather
than a local-core raw capability-source change. The affected meeting-shell
user-facing strings are covered by the i18n message registry.

This does not close the full product-semantics program. The meeting shell now
uses registry-backed object completion for object mentions instead of direct
owner-API fallbacks, and the current generated asset, storyboard, storyboard
scene, and character paths are verified. The remaining work is broader pack
object coverage, affordance coverage, and search-ranking quality across the
registry.
