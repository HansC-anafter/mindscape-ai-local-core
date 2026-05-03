# Tool Retrieval and Resource Bindings

Mindscape AI Local Core uses tool retrieval and workspace resource bindings to select a small, relevant tool inventory for workspace chat, meeting orchestration, filtered tool APIs, and dispatch planning.

This page describes the released public architecture scope for the current repository.

## Retrieval Corpus

The retrieval corpus contains local tool entries and playbook entries collected from Local Core host services.

Each corpus entry carries host-visible identity, description, category, and optional affordance metadata. The retrieval layer treats playbooks as indexable execution options, but it does not expose private playbook implementation details as part of this public contract.

## Embedding Store

Tool retrieval uses a PostgreSQL pgvector-backed embedding store for local tool and playbook discovery.

Indexed entries can carry bounded identity, description, category, model, lexical, and affordance metadata. Lexical metadata supports keyword search alongside vector similarity. Affordance metadata lets retrieval find playbooks by declared resource needs when the caller has structured asset types instead of only a natural language query.

## Model Selection and Indexing

The active embedding model is resolved from local configuration and available runtime settings.

After the API is ready, Local Core can warm the shared retrieval corpus and refresh stale retrieval data.

This keeps tool retrieval out of the API bind path while still allowing the retrieval corpus to refresh after local capabilities or playbooks change.

## Retrieval Path

The primary retrieval helper accepts a query, a result limit, and optional workspace context. It can use short-lived caching to avoid repeated retrieval work within a turn.

Retrieval can combine vector similarity, lexical search, and indexed model fallback. The search path is an implementation detail; the public contract is that callers receive bounded, ranked local tool or playbook candidates.

Callers are expected to fall back to bounded defaults or installed manifest scans when retrieval misses or errors.

## Workspace Resource Bindings

Workspace resource bindings are the workspace overlay for shared resources. A binding can attach a playbook, tool, data source, or asset to a workspace with an access mode and local overrides.

For tools, explicit `TOOL` bindings are the strongest signal. When a workspace has explicit tool bindings, the retrieval helper filters semantic matches to that allowlist. Prompt context assembly can also append explicitly bound tools that semantic retrieval did not surface, so manually bound tools remain visible to the workspace.

The public boundary is that bindings describe workspace-local availability and overrides. They do not grant unrestricted execution. Execution still passes through policy gates, dispatch gates, runtime availability checks, and executor-specific validation.

## Chat and Meeting Use

Workspace chat context can request relevant tools for the current message and inject an `Available Tools` section when matches or explicit bindings exist.

Meeting orchestration pre-fetches relevant tools from agenda items and the user request. The meeting prompt layer then builds tool inventory in this order:

- explicit workspace tool bindings, with matching retrieval hits shown first when available
- retrieval hits when there are no explicit tool bindings
- installed manifest scan as a last resort

During action extraction, the meeting layer can re-query retrieval for action items that have no tool or playbook actuator. It only fills a tool or playbook reference when retrieval improves binding coverage for those unbound items.

## Filtered Tool APIs

The filtered tool API can use a task hint to retrieve semantically relevant tools and combine them with safe default tools. On retrieval miss or retrieval error, it fails open to safe defaults and optional recommended capability tools instead of returning an empty tool set.

The dedicated retrieval endpoint is a discovery and filtering aid, not an execution endpoint.

## Public Boundary

Local Core owns local tool and playbook indexing, pgvector-backed retrieval, lexical search support, short-lived retrieval caching, workspace resource bindings, prompt inventory construction, and filtered tool discovery.

Local Core does not publicly own:

- provider-native tool payloads
- external account setup or credential lifecycle
- private prompt text
- unrestricted execution authorization
- installed capability implementation internals
- internal authoring guides or historical implementation plans

Public documentation should describe stable retrieval and binding responsibilities. Internal authoring workflows, private manifests, dated work logs, private validation material, and migration notes remain withheld.
