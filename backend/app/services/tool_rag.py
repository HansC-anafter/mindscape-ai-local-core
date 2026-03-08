"""
Tool RAG retrieval helper.

Thin wrapper over ToolEmbeddingService.search() for use in meeting engine
and workspace chat ContextBuilder.

P2 — Process-level TTL cache
-----------------------------
`retrieve_relevant_tools` is called up to **twice per chat turn** by
ContextBuilder (build_qa_context + build_planning_context) and once per
meeting turn by MeetingEngine (pre-fetch).  Because Ollama embed +
pgvector query takes ~40–80 ms, caching the same query within a short
window cuts latency noticeably.

Cache key: (query_normalised, workspace_id_or_empty, top_k)
TTL: 60 seconds (covers the lifetime of a single turn round-trip; stale
     after a minute so new tool installs are picked up quickly).
Max entries: 256 (protects against memory blow-up).
"""

import hashlib
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Process-level cache
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS: float = 60.0
_CACHE_MAX_ENTRIES: int = 256

# {cache_key: (expire_at: float, result: list[dict])}
_cache: dict[str, tuple[float, list[dict]]] = {}


def _make_key(query: str, workspace_id: Optional[str], top_k: int) -> str:
    """Stable cache key independent of whitespace variation."""
    normalised = " ".join(query.lower().split())
    raw = f"{normalised}|{workspace_id or ''}|{top_k}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[list[dict]]:
    entry = _cache.get(key)
    if entry is None:
        return None
    expire_at, result = entry
    if time.monotonic() > expire_at:
        _cache.pop(key, None)
        return None
    return result


def _cache_set(key: str, result: list[dict]) -> None:
    # Evict oldest entries when at capacity (simple FIFO)
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        oldest_key = next(iter(_cache))
        _cache.pop(oldest_key, None)
    _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, result)


def invalidate_tool_rag_cache() -> None:
    """Clear the entire cache — call after tool installs/uninstalls."""
    _cache.clear()
    logger.debug("Tool RAG cache invalidated")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def retrieve_relevant_tools(
    query: str,
    top_k: int = 15,
    workspace_id: Optional[str] = None,
) -> list[dict]:
    """Return top-K tools semantically relevant to *query*.

    If *workspace_id* is provided and the workspace has explicit TOOL
    resource bindings, results are filtered to the binding allowlist.

    Returns a list of dicts: [{"tool_id": ..., "display_name": ..., "description": ...}]
    sorted by similarity descending.

    Returns [] on RAG miss or error — callers must fall back to manifest scan.

    Results are cached per (query, workspace_id, top_k) for
    ``_CACHE_TTL_SECONDS`` seconds to avoid redundant Ollama calls within
    the same turn.
    """
    cache_key = _make_key(query, workspace_id, top_k)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(
            "Tool RAG cache hit (key=%s, %d results)", cache_key[:8], len(cached)
        )
        return cached

    result = await _retrieve_from_service(query, top_k, workspace_id)
    _cache_set(cache_key, result)
    return result


async def _retrieve_from_service(
    query: str,
    top_k: int,
    workspace_id: Optional[str],
) -> list[dict]:
    """Actual retrieval — called only on cache miss.

    Prefers multi-model RRF search when more than one embedding model is
    indexed; falls back to single-model search() gracefully.
    """
    try:
        from backend.app.services.tool_embedding_service import (
            ToolEmbeddingService,
            RAG_HIT,
        )

        svc = ToolEmbeddingService()
        # search_rrf() automatically falls back to single-model when only one
        # model is indexed, so this is always safe to call.
        matches, status = await svc.search_rrf(query, top_k=top_k)
        if status != RAG_HIT or not matches:
            return []

        results = [
            {
                "tool_id": m.tool_id,
                "display_name": m.display_name,
                "description": m.description,
            }
            for m in matches
        ]

        # Per-capability diversity: cap each capability prefix so that large
        # packs (e.g. ig=28 tools) don't crowd out smaller ones (frontier_research=3).
        cap_counts: dict[str, int] = {}
        max_per_cap = 5
        diversified: list[dict] = []
        for r in results:
            tid = r["tool_id"]
            cap = tid.split(".")[0] if "." in tid else "_builtin"
            cap_counts[cap] = cap_counts.get(cap, 0) + 1
            if cap_counts[cap] <= max_per_cap:
                diversified.append(r)
        results = diversified

        if not workspace_id:
            return results

        # Filter by explicit TOOL binding allowlist when workspace_id is available
        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType

            store = WorkspaceResourceBindingStore()
            bindings = store.list_bindings_by_workspace(
                workspace_id, resource_type=ResourceType.TOOL
            )
            if bindings:
                allowed = {b.resource_id for b in bindings}
                filtered = [r for r in results if r["tool_id"] in allowed]
                logger.debug(
                    "Tool RAG: %d matches → %d after workspace allowlist filter",
                    len(results),
                    len(filtered),
                )
                return filtered
        except Exception as exc:
            logger.debug("Allowlist filter failed (returning unfiltered): %s", exc)

        return results

    except Exception as exc:
        logger.debug("retrieve_relevant_tools failed: %s", exc)
        return []
