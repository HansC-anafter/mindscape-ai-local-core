"""Bind compiler graph topology to the writer-authoritative ACL cohort."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

from .contracts import GraphCommunityWrite, GraphProjectionWrite


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def bind_graph_visibility(
    graph: GraphProjectionWrite,
    *,
    visibility_partition_hash: str,
) -> GraphProjectionWrite:
    """Re-key derived graph rows without changing compiler-owned topology.

    Capability compilers cannot authoritatively observe the current ACL label.
    The single projection writer binds their output after locking the resource,
    so an ACL replacement followed by reindex cannot reuse a stale visibility
    partition or require pack-specific authorization reads.
    """

    if len(visibility_partition_hash) != 64:
        raise ValueError("knowledge_graph_visibility_partition_hash_invalid")
    if graph.visibility_partition_hash == visibility_partition_hash:
        return graph

    community_key_map = {
        community.community_key: (
            "community:"
            + _hash(
                {
                    "visibility_partition_hash": visibility_partition_hash,
                    "algorithm_revision": graph.algorithm_revision,
                    "community_key": community.community_key,
                    "level": community.level,
                    "entity_keys": community.entity_keys,
                    "relation_keys": community.relation_keys,
                }
            )
        )
        for community in graph.communities
    }
    communities = tuple(
        _bind_community(
            community,
            visibility_partition_hash=visibility_partition_hash,
            community_key_map=community_key_map,
        )
        for community in graph.communities
    )
    reports = tuple(
        replace(
            report,
            community_key=community_key_map[report.community_key],
        )
        for report in graph.reports
    )
    return replace(
        graph,
        visibility_partition_hash=visibility_partition_hash,
        communities=communities,
        reports=reports,
    )


def _bind_community(
    community: GraphCommunityWrite,
    *,
    visibility_partition_hash: str,
    community_key_map: dict[str, str],
) -> GraphCommunityWrite:
    bound_key = community_key_map[community.community_key]
    bound_parent = (
        community_key_map[community.parent_community_key]
        if community.parent_community_key
        else None
    )
    return replace(
        community,
        community_key=bound_key,
        parent_community_key=bound_parent,
        affected_subgraph_hash=_hash(
            {
                "visibility_partition_hash": visibility_partition_hash,
                "community_key": bound_key,
                "source_hash": community.affected_subgraph_hash,
            }
        ),
        full_rebuild_hash=_hash(
            {
                "visibility_partition_hash": visibility_partition_hash,
                "community_key": bound_key,
                "parent_community_key": bound_parent,
                "source_hash": community.full_rebuild_hash,
            }
        ),
    )


__all__ = ["bind_graph_visibility"]
