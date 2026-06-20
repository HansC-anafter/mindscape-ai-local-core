"""Embedding generation helpers for ToolEmbeddingService."""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional, Tuple

from backend.app.services.tool_embedding_service_core import NOMIC_MODELS

logger = logging.getLogger(__name__)


async def generate_embedding(
    service: Any, text: str, *, is_query: bool = True
) -> Tuple[Optional[List[float]], Optional[str]]:
    """Generate an embedding through the existing VectorSearchService path."""
    try:
        from backend.app.services.vector_search import VectorSearchService

        vs = VectorSearchService(postgres_config=service.postgres_config)
        embedding, model_name = await vs._generate_embedding_with_model(
            text, is_query=is_query
        )
        return embedding, model_name
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
        return None, None


async def generate_embedding_for_model(
    service: Any, text: str, model_name: str, *, is_query: bool = True
) -> Tuple[Optional[List[float]], Optional[str]]:
    """Generate an embedding using a specific Ollama model."""
    prompt_text = text
    base_model = model_name.split(":")[0].lower()
    if base_model in NOMIC_MODELS:
        prefix = "search_query" if is_query else "search_document"
        prompt_text = f"{prefix}: {text}"

    try:
        import httpx

        ollama_url = (
            os.getenv("OLLAMA_HOST", "").strip()
            or "http://host.docker.internal:11434"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model_name, "prompt": prompt_text},
            )
            if resp.status_code == 200:
                emb = resp.json().get("embedding")
                if emb:
                    return emb, model_name
            if ollama_url == "http://host.docker.internal:11434":
                resp2 = await client.post(
                    "http://ollama:11434/api/embeddings",
                    json={"model": model_name, "prompt": prompt_text},
                )
                if resp2.status_code == 200:
                    emb2 = resp2.json().get("embedding")
                    if emb2:
                        return emb2, model_name
    except Exception as e:
        logger.debug(f"_generate_embedding_for_model({model_name}) failed: {e}")
    return None, None
