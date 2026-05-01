# Addressable Object Layer

This directory defines the platform-side architecture for turning pack-owned
entities into stable addressable objects that can be selected, referenced,
brought into meetings, and materialized back into owner-pack state.

## Why This Exists

The target is not a pack-specific toolbar rollout.

The target is a runtime layer where:

- a user can select something meaningful on screen
- Local-Core resolves that selection into a stable object reference
- the meeting runtime can consume that object with bounded context
- downstream packs can return proposals, previews, handoffs, or canonical writeback

## Runtime Ownership

The runtime host for this system remains `mindscape-ai-local-core`.

- Local-Core owns selection state, contextual launch surfaces, meeting attachment,
  graph projection, and runtime catalog APIs.
- Capability packs own their canonical schemas, business rules, storage, and
  object-specific resolvers/materializers.

## Read Order

1. [Object Model And Identity](./object-model-and-identity.md)
2. [Selection And Contextual Action Runtime](./selection-and-contextual-action-runtime.md)
3. [Meeting Attachment And Materialization](./meeting-attachment-and-materialization.md)
4. [Graph And Projection Surfaces](./graph-and-projection-surfaces.md)
5. [Rollout Phases And Runtime Adoption](./rollout-phases-and-runtime-adoption.md)

## Companion Docs

- Pack authoring and manifest-side contracts live in:
  the capability-source authoring docs
- Runtime API/spec lives in:
  `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs/api/addressable-object-layer-runtime-api.md`
- Active implementation tracking lives in:
  `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/2026-04-23/addressable-object-layer/`
- Current interoperability/usability assessment lives in:
  `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/2026-04-23/addressable-object-layer/platform-compatibility-and-cross-pack-usability-assessment.md`

## Core Terms

- `Addressable object`: a thing with a stable identity, owner, type, summary, and relations.
- `ObjectRef`: the minimal transport identity used across runtime surfaces.
- `Resolver`: pack-owned code that expands an `ObjectRef` into summary, detail, relations, and actions.
- `Projection`: a runtime view such as graph, toolbar popover, meeting context, or review lane.
- `Materializer`: pack-owned code that converts a meeting result into proposal, preview, handoff, or canonical writeback.
