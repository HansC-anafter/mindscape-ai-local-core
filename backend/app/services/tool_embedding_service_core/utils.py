"""Pure helpers for ToolEmbeddingService."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .types import ToolMatch


def vector_to_pg_literal(values: Sequence[float]) -> str:
    """Convert an embedding vector into the pgvector literal format."""
    return "[" + ",".join(str(value) for value in values) + "]"


def build_embed_text(
    display_name: str,
    description: str,
    capability_context: str | None = None,
) -> str:
    """Build the embedding text used for tool and playbook indexing."""
    embed_text = f"{display_name}: {description}"
    if capability_context:
        return f"{embed_text}. {capability_context}"
    return embed_text


def mapping_row_to_tool_match(row: Mapping[str, Any]) -> ToolMatch:
    """Build a ToolMatch from a dict-like database row."""
    return ToolMatch(
        tool_id=str(row["tool_id"]),
        display_name=str(row.get("display_name") or ""),
        description=str(row["description"]),
        category=str(row.get("category") or ""),
        capability_code=row.get("capability_code"),
        similarity=float(row["similarity"]),
    )


def tuple_row_to_tool_match(row: Sequence[Any], similarity: float | None = None) -> ToolMatch:
    """Build a ToolMatch from a tuple-style database row."""
    resolved_similarity = similarity if similarity is not None else float(row[5])
    return ToolMatch(
        tool_id=str(row[0]),
        display_name=str(row[1] or row[0]),
        description=str(row[2]),
        category=str(row[3] or ""),
        capability_code=row[4],
        similarity=resolved_similarity,
    )


def filter_mapping_rows_by_score(
    rows: Iterable[Mapping[str, Any]],
    *,
    min_score: float,
) -> list[ToolMatch]:
    """Convert rows into ToolMatch values after applying the score threshold."""
    matches: list[ToolMatch] = []
    for row in rows:
        similarity = float(row["similarity"])
        if similarity < min_score:
            continue
        matches.append(mapping_row_to_tool_match(row))
    return matches


def fuse_ranked_tool_matches(
    *,
    per_model_results: Iterable[Sequence[ToolMatch]],
    bm25_results: Sequence[ToolMatch],
    top_k: int,
    min_score: float,
    rrf_k: int,
) -> list[ToolMatch]:
    """Fuse multiple ranked ToolMatch lists with Reciprocal Rank Fusion."""
    rrf_scores: dict[str, float] = {}
    tool_meta: dict[str, ToolMatch] = {}
    best_similarity: dict[str, float] = {}

    for ranked_list in per_model_results:
        for rank, match in enumerate(ranked_list):
            tool_id = match.tool_id
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0.0) + 1.0 / (
                rrf_k + rank + 1
            )
            tool_meta[tool_id] = match
            best_similarity[tool_id] = max(
                best_similarity.get(tool_id, 0.0),
                match.similarity,
            )

    for rank, match in enumerate(bm25_results):
        tool_id = match.tool_id
        rrf_scores[tool_id] = rrf_scores.get(tool_id, 0.0) + 1.0 / (rrf_k + rank + 1)
        if tool_id not in tool_meta:
            tool_meta[tool_id] = match
            best_similarity[tool_id] = 0.0
        best_similarity[tool_id] = max(best_similarity.get(tool_id, 0.0), min_score)

    matches: list[ToolMatch] = []
    for tool_id in sorted(rrf_scores, key=lambda item: rrf_scores[item], reverse=True)[
        :top_k
    ]:
        if best_similarity.get(tool_id, 0.0) < min_score:
            continue
        meta = tool_meta[tool_id]
        matches.append(
            ToolMatch(
                tool_id=meta.tool_id,
                display_name=meta.display_name,
                description=meta.description,
                category=meta.category,
                capability_code=meta.capability_code,
                similarity=rrf_scores[tool_id],
            )
        )

    return matches
