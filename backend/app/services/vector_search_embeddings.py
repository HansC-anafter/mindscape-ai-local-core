"""
Embedding generation helpers for VectorSearchService.
"""

from dataclasses import dataclass
import logging
import os
import time
from typing import List, Optional

from backend.app.services.vector_search_ollama import OllamaEmbeddingClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingGenerationReceipt:
    """Internal embedding result with provider identity."""

    embedding: tuple[float, ...]
    provider: str
    model: str

    @property
    def dimension(self) -> int:
        return len(self.embedding)


class VectorEmbeddingGenerator:
    """Generate embeddings through the existing Ollama-first fallback path."""

    def __init__(
        self,
        *,
        ollama_client: OllamaEmbeddingClient | None = None,
    ) -> None:
        self.ollama_client = ollama_client or OllamaEmbeddingClient()

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate an embedding for query text using the configured model.

        Args:
            text: Text to embed

        Returns:
            Embedding vector, or None when no provider succeeds.
        """
        ollama_embedding = await self.generate_ollama_embedding(text)
        if ollama_embedding:
            return ollama_embedding

        return await self.generate_openai_embedding(text)

    async def generate_embedding_with_model(
        self, text: str, *, is_query: bool = True
    ) -> tuple[Optional[List[float]], Optional[str]]:
        """
        Generate an embedding and return the model name used.

        Args:
            text: Text to embed
            is_query: True for search, False for indexing

        Returns:
            Tuple of embedding and model name, or (None, None) if generation failed.
        """
        receipt = await self.generate_embedding_receipt(
            text,
            is_query=is_query,
        )
        if receipt is None:
            return None, None
        return list(receipt.embedding), receipt.model

    async def generate_embedding_receipt(
        self,
        text: str,
        *,
        is_query: bool = True,
        allow_openai_fallback: bool = True,
    ) -> EmbeddingGenerationReceipt | None:
        """Generate one vector while preserving provider and model identity."""

        preferred = await self.ollama_client.select_embedding_model(
            os.getenv("OLLAMA_EMBED_MODEL", "")
        )
        ollama_outcome = await self.ollama_client.embed(
            text,
            model=preferred,
            is_query=is_query,
        )
        if ollama_outcome.ok:
            return EmbeddingGenerationReceipt(
                embedding=ollama_outcome.embedding,
                provider="ollama",
                model=preferred,
            )

        if not allow_openai_fallback:
            return None
        openai_embedding = await self.generate_openai_embedding(text)
        if openai_embedding:
            return EmbeddingGenerationReceipt(
                embedding=tuple(openai_embedding),
                provider="openai",
                model=self._configured_openai_model_name(),
            )
        return None

    async def probe_embedding_provider(
        self,
        text: str = "mindscape embedding provider admission",
    ) -> dict[str, object]:
        """Return a bounded provider receipt without embedding content."""

        started = time.monotonic()
        receipt = await self.generate_embedding_receipt(
            text,
            is_query=False,
            allow_openai_fallback=False,
        )
        elapsed = round(time.monotonic() - started, 6)
        if receipt is None:
            return {
                "ok": False,
                "provider": None,
                "model": None,
                "dimension": 0,
                "elapsed_seconds": elapsed,
                "error_code": "embedding_provider_unavailable",
            }
        return {
            "ok": True,
            "provider": receipt.provider,
            "model": receipt.model,
            "dimension": receipt.dimension,
            "elapsed_seconds": elapsed,
            "error_code": None,
        }

    def get_ollama_url(self) -> Optional[str]:
        """
        Return a reachable Ollama base URL, or None.

        Returns:
            Reachable Ollama URL if the tags endpoint responds.
        """
        return self.ollama_client.get_reachable_base_url()

    async def generate_ollama_embedding(
        self, text: str, model: Optional[str] = None, *, is_query: bool = True
    ) -> Optional[List[float]]:
        """
        Generate an embedding using an Ollama local model.

        Args:
            text: Text to embed
            model: Exact model name to use
            is_query: True for search queries, False for indexing documents

        Returns:
            Embedding vector, or None when Ollama is unavailable.
        """
        embed_model = model or os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
        outcome = await self.ollama_client.embed(
            text,
            model=embed_model,
            is_query=is_query,
        )
        return list(outcome.embedding) if outcome.ok else None

    @staticmethod
    def _configured_openai_model_name() -> str:
        try:
            from backend.app.services.system_settings_store import (
                SystemSettingsStore,
            )

            embedding_setting = SystemSettingsStore().get_setting(
                "embedding_model"
            )
            return (
                str(embedding_setting.value)
                if embedding_setting
                else "text-embedding-3-small"
            )
        except Exception:
            return "text-embedding-3-small"

    async def generate_openai_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate an embedding using the OpenAI API fallback.

        Args:
            text: Text to embed

        Returns:
            Embedding vector, or None when OpenAI is unavailable.
        """
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore
            from backend.app.services.config_store import ConfigStore
            from backend.app.services.mindscape_store import MindscapeStore

            settings_store = SystemSettingsStore()
            embedding_setting = settings_store.get_setting("embedding_model")

            if not embedding_setting:
                logger.warning(
                    "No embedding model configured, using default: text-embedding-3-small"
                )
                model_name = "text-embedding-3-small"
            else:
                model_name = str(embedding_setting.value)

            config_store = ConfigStore()
            MindscapeStore().ensure_default_profile()

            config = config_store.get_or_create_config("default-user")
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")

            if not api_key:
                logger.warning("OpenAI API key not configured for embedding generation")
                return None

            import openai

            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(model=model_name, input=text)

            embedding = response.data[0].embedding
            logger.debug(
                "Generated OpenAI embedding using model: %s (dimension: %d)",
                model_name,
                len(embedding),
            )
            return embedding

        except Exception as e:
            logger.error("Failed to generate OpenAI embedding: %s", e)
            return None
