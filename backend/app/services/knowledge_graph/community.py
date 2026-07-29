"""Deterministic visibility-partitioned community decomposition baseline."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from .contracts import (
    GraphCommunityWrite,
    GraphEntityWrite,
    GraphRelationWrite,
)


def _hash(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def build_visibility_partitioned_communities(
    *,
    entities: Iterable[GraphEntityWrite],
    relations: Iterable[GraphRelationWrite],
    visibility_partition_hash: str,
) -> tuple[GraphCommunityWrite, ...]:
    """Build deterministic connected communities without crossing one ACL cohort."""

    entity_keys = sorted({entity.canonical_key for entity in entities})
    relation_rows = tuple(relations)
    adjacency = {key: set() for key in entity_keys}
    for relation in relation_rows:
        adjacency.setdefault(relation.source_entity_key, set()).add(
            relation.target_entity_key
        )
        adjacency.setdefault(relation.target_entity_key, set()).add(
            relation.source_entity_key
        )
    communities: list[GraphCommunityWrite] = []
    visited: set[str] = set()
    for seed in sorted(adjacency):
        if seed in visited:
            continue
        stack = [seed]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))
        member_tuple = tuple(sorted(members))
        relation_keys = tuple(
            sorted(
                {
                    relation.relation_key
                    for relation in relation_rows
                    if relation.source_entity_key in members
                    and relation.target_entity_key in members
                }
            )
        )
        generation_payload = {
            "visibility_partition_hash": visibility_partition_hash,
            "entities": member_tuple,
            "relations": relation_keys,
            "algorithm": "connected_components.v1",
        }
        digest = _hash(generation_payload)
        communities.append(
            GraphCommunityWrite(
                community_key=f"community:{digest}",
                level=0,
                parent_community_key=None,
                entity_keys=member_tuple,
                relation_keys=relation_keys,
                affected_subgraph_hash=digest,
                full_rebuild_hash=digest,
            )
        )
    return tuple(communities)


__all__ = ["build_visibility_partitioned_communities"]
