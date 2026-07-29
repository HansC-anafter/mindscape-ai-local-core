"""Explicit graph bounds; no LLM router or hidden retry lives here."""

from __future__ import annotations


MODE_BOUNDS = {
    "hybrid": {"max_candidates": 60},
    "local_graph": {"max_hops": 2, "max_nodes": 200, "max_edges": 400},
    "multi_hop": {"max_hops": 3, "max_nodes": 400, "max_edges": 800},
    "global_graph": {"max_reports": 40},
}


def bounds_for_mode(mode: str) -> dict[str, int]:
    try:
        return dict(MODE_BOUNDS[mode])
    except KeyError as exc:
        raise ValueError("knowledge_query_retrieval_mode_forbidden") from exc


__all__ = ["MODE_BOUNDS", "bounds_for_mode"]
