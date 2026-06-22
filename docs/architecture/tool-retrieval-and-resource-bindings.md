# Tool Retrieval and Resource Bindings

Mindscape AI Local Core uses tool retrieval and workspace resource bindings to select a small, relevant tool inventory for workspace chat, meeting orchestration, filtered tool surfaces, and dispatch planning.

This page describes the released public architecture scope for the current repository.

## Retrieval Corpus

The retrieval corpus contains local tool entries and playbook entries collected from Local Core host services.

Each corpus entry carries host-visible identity, description, category, and optional affordance metadata. The retrieval layer treats playbooks as indexable execution options. Playbook implementation details stay with the playbook owner.

## Embedding Store

Tool retrieval uses a PostgreSQL pgvector-backed embedding store for local tool and playbook discovery.

Indexed entries can carry bounded identity, description, category, model, lexical, and affordance metadata. Lexical metadata supports keyword search alongside vector similarity. Affordance metadata lets retrieval find playbooks by declared resource needs when the caller has structured asset types.

## Model Selection and Indexing

The active embedding model is resolved from local configuration and available runtime settings.

After application startup, Local Core can warm the shared retrieval corpus and refresh stale retrieval data.

This keeps request handling focused on selection while the retrieval corpus refreshes after local capabilities or playbooks change.

## Retrieval Path

The primary retrieval helper accepts a query, a result limit, and optional workspace context. It can use short-lived caching for repeated retrieval work within a turn.

Retrieval can combine vector similarity, lexical search, and indexed model fallback. The search path is an implementation detail; the public contract is that callers receive bounded, ranked local tool or playbook candidates.

Callers are expected to fall back to bounded defaults or installed manifest scans when retrieval misses or errors.

## Workspace Resource Bindings

Workspace resource bindings are the workspace overlay for shared resources. A binding can attach a playbook, tool, data source, or asset to a workspace with an access mode and local overrides.

For tools, explicit `TOOL` bindings are the strongest signal. When a workspace has explicit tool bindings, the retrieval helper filters semantic matches to that allowlist. Context assembly can also append explicitly bound tools when semantic retrieval misses them, so manually bound tools remain visible to the workspace.

The public boundary is that bindings describe workspace-local availability and overrides. Execution still passes through policy gates, dispatch gates, runtime availability checks, and executor-specific validation.

## Chat and Meeting Use

Workspace chat context can request relevant tools for the current message and inject an `Available Tools` section when matches or explicit bindings exist.

Meeting orchestration pre-fetches relevant tools from agenda items and the user request. The meeting assembly path then builds tool inventory in this order:

- explicit workspace tool bindings, with matching retrieval hits shown first when available
- retrieval hits when there are no explicit tool bindings
- installed manifest scan as a last resort

During action extraction, the meeting layer can re-query retrieval for action items that have no tool or playbook actuator. It only fills a tool or playbook reference when retrieval improves binding coverage for those unbound items.

## Filtered Tool Surfaces

Filtered tool surfaces can use a task hint to retrieve semantically relevant tools and combine them with safe default tools. On retrieval miss or retrieval error, they fall back to safe defaults and optional recommended capability tools.

The dedicated retrieval surface is a discovery and filtering aid. Execution still runs through policy, dispatch, and executor gates.

## Public Boundary

Local Core owns local tool and playbook indexing, pgvector-backed retrieval, lexical search support, short-lived retrieval caching, workspace resource bindings, context inventory construction, and filtered tool discovery.

Related owners keep:

- adapter tool payloads
- external account setup or credential lifecycle
- assembly text
- unrestricted execution authorization
- installed capability implementation internals
- authoring guides or historical implementation plans

Public documentation describes stable retrieval and binding responsibilities. Authoring workflows, manifests, dated operational records, verification captures, and migration notes stay in owner-managed records.
