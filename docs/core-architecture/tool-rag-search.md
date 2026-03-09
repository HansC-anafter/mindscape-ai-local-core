# Tool RAG Search Architecture

> **Status**: Implemented
> **Last Updated**: 2026-03-07
> **Key Files**:
> - `backend/app/services/tool_embedding_service.py`
> - `backend/app/services/tool_rag.py`

This document describes the Tool RAG (Retrieval-Augmented Generation) search system that powers tool discovery in Mindscape AI. Tool RAG allows the meeting engine and conversation context builder to semantically retrieve relevant tools for a given user query, without requiring exact name matching.

---

## Overview

Tool RAG solves the tool discovery problem: given a user query (e.g. "post to Instagram"), which tools should the AI consider invoking?

```text
User Query
    ↓
retrieve_relevant_tools()
    ↓ cache hit?  → return cached result
    ↓
search_rrf()                      ← multi-model fusion
    ├─ embed query (bge-m3)
    ├─ embed query (nomic-embed-text)
    ├─ parallel pgvector queries
    └─ Reciprocal Rank Fusion
    ↓
workspace allowlist filter (if workspace_id)
    ↓
[{ tool_id, display_name, description }]
```

---

## Components

### 1. ToolEmbeddingService (`tool_embedding_service.py`)

Manages the `tool_embeddings` pgvector table. Each tool has one row per embedding model (unique on `(tool_id, embedding_model)`).

| Method | Purpose |
|--------|---------|
| `ensure_indexed()` | Cold-start hook: probes all Ollama embed models, indexes any stale model |
| `index_all_tools()` | Index all tools with primary model |
| `index_all_tools_multimodel()` | Index all tools for every available Ollama embed model |
| `_index_all_tools_for_model(model)` | Index all tools for a specific model |
| `search(query, top_k, min_score)` | Single-model cosine similarity search |
| `search_rrf(query, top_k, rrf_k)` | Multi-model Reciprocal Rank Fusion search |
| `get_indexed_models()` | Query DB for distinct indexed model names |
| `_search_single_model(emb, model, top_k)` | Per-model vector search (no threshold) |
| `_generate_embedding(text)` | Generate embedding via VectorSearchService |
| `_generate_embedding_for_model(text, model)` | Force-generate embedding for a specific Ollama model |
| `invalidate_tool_rag_cache()` | Clear the process-level cache (called after installs) |


### 2. Tool RAG cache (`tool_rag.py`)

A process-level TTL cache wrapping `search_rrf()`. Avoids redundant Ollama + pgvector calls within a single turn.

| Property | Value |
|----------|-------|
| TTL | 60 seconds |
| Max entries | 256 |
| Cache key | MD5(`normalized_query \| workspace_id \| top_k`) |
| Eviction | FIFO when at capacity |
| Invalidation | `invalidate_tool_rag_cache()` — called after capability install/enable |

---

## Embedding Model Priority

The primary embedding model is selected in this order:

| Priority | Source | Description |
|----------|--------|-------------|
| P1 | Frontend Settings (`ollama_embed_model`) | Explicit admin configuration |
| P2 | `OLLAMA_EMBED_MODEL` env var | Environment override |
| P3a | Ollama auto-detect: `bge-m3` | Preferred: best multilingual quality |
| P3b | Ollama auto-detect: `nomic-embed-text` | Fallback Ollama model |
| P4 | Frontend Settings (`embedding_model`) | OpenAI model from settings |
| P5 | `text-embedding-3-small` | Final default |

---

## Multi-Model RRF Search

When multiple embedding models have indexed data, `search_rrf()` fuses their result lists using **Reciprocal Rank Fusion**:

```
RRF score(tool) = Σ  1 / (k + rank_i)
                 i
```

where `k = 60` (default) dampens the impact of top-ranked items and `rank_i` is the 0-based position of the tool in model `i`'s result list.

### Why RRF?

- `bge-m3` excels at multilingual semantic understanding (English + Chinese both)
- `nomic-embed-text` provides complementary English-centric representations
- Tools that rank highly in **both** models rise to the top; model-specific quirks are dampened
- RRF is parameter-light and robust compared to score fusion

### Fallback Behavior

| Condition | Behavior |
|-----------|---------|
| Only 1 model indexed | Falls back to `search()` (no overhead) |
| Embedding generation fails for a model | Skips that model, continues with remaining |
| All embeddings fail | Returns `RAG_ERROR`, caller falls back to manifest scan |

---

## Cold Start — `ensure_indexed()`

Called at backend startup. Automatically discovers all available Ollama embedding models and indexes any that are stale:

```text
Backend starts
    ↓
ensure_indexed()
    ↓
probe Ollama /api/tags
    ├─ bge-m3:          48 rows / 48 expected → up to date
    └─ nomic-embed-text:  0 rows / 48 expected → stale → index
    ↓
_index_all_tools_for_model("nomic-embed-text")
    ↓
next search_rrf() → "Tool RRF (2 models): N matches"
```

Ollama embed models are identified by keyword matching: `embed`, `bge`, `nomic`, `e5`, `gte`.

---

## Database Schema

```sql
CREATE TABLE tool_embeddings (
    id              SERIAL PRIMARY KEY,
    tool_id         TEXT NOT NULL,
    display_name    TEXT,
    description     TEXT NOT NULL,
    category        TEXT,
    capability_code TEXT,
    embedding       vector,
    embedding_model TEXT NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tool_id, embedding_model)
);
```

The `UNIQUE (tool_id, embedding_model)` constraint is what enables multi-model storage: each tool can have one row per model, all within the same table.

---

## Cache Invalidation Hooks

The tool RAG cache is automatically cleared after tool re-indexing:

| Trigger | Location |
|---------|---------|
| Capability pack installed | `capability_install.py:_bg_reindex()` |
| Capability pack enabled | `capability_packs.py:_bg_reindex()` |
| Manual | `invalidate_tool_rag_cache()` |

---

## Integration Points

### Meeting Engine

`MeetingPromptsMixin._build_tool_inventory_block()` calls `retrieve_relevant_tools()` once per turn, using the session's user message as the query. Results are injected into the executor/planner/critic prompts.

### Context Builder

`ContextBuilder` may call `retrieve_relevant_tools()` to populate tool suggestions in the workspace chat context.

### Workspace Allowlist Filter

When `workspace_id` is provided, results are filtered against explicit `TOOL` resource bindings from `WorkspaceResourceBindingStore`. This allows admins to restrict which tools are surfaced per workspace.

---

## Configuration Reference

| Setting | Location | Effect |
|---------|---------|--------|
| `ollama_embed_model` | Frontend Settings → Tool RAG tab | Override embed model (P1) |
| `embedding_model` | Frontend Settings → Knowledge Embedding tab | OpenAI fallback (P4) |
| `OLLAMA_EMBED_MODEL` | Environment variable | Env override (P2) |
| `OLLAMA_HOST` | Environment variable | Ollama base URL |

---

## Related Documents

- [Memory & Intent Architecture](./memory-intent-architecture.md)
- [Prompt Compilation](./prompt-compilation.md)
- [Capability Pack Development Guide](../capability-pack-development-guide.md)
- [Runtime Environments](./runtime-environments.md)
