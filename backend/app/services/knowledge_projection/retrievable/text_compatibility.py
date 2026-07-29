"""The one physical compatibility contract for external_docs text vectors."""

from __future__ import annotations

from typing import Iterable


EXTERNAL_DOCS_VECTOR_DIMENSION = 1536


def fit_external_docs_embedding(embedding: Iterable[float]) -> list[float]:
    """Zero-pad shorter vectors; cosine distance is preserved."""

    values = [float(value) for value in embedding]
    if len(values) > EXTERNAL_DOCS_VECTOR_DIMENSION:
        raise ValueError(
            "document_embedding_dimension_exceeds_external_docs:"
            f"{len(values)}:{EXTERNAL_DOCS_VECTOR_DIMENSION}"
        )
    if not values:
        raise ValueError("document_embedding_is_empty")
    return values + [0.0] * (EXTERNAL_DOCS_VECTOR_DIMENSION - len(values))


__all__ = ["EXTERNAL_DOCS_VECTOR_DIMENSION", "fit_external_docs_embedding"]
