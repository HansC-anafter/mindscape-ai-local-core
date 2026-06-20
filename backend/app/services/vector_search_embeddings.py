"""
Embedding generation helpers for VectorSearchService.
"""

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


class VectorEmbeddingGenerator:
    """Generate embeddings through the existing Ollama-first fallback path."""

    _NOMIC_MODELS = {"nomic-embed-text", "nomic-embed-text-v1.5"}

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
        preferred = os.getenv("OLLAMA_EMBED_MODEL", "").strip()
        if not preferred:
            try:
                import httpx

                ollama_url = self.get_ollama_url()
                if ollama_url:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        response = await client.get(f"{ollama_url}/api/tags")
                        if response.status_code == 200:
                            names = [
                                model["name"].split(":")[0]
                                for model in response.json().get("models", [])
                            ]
                            if "bge-m3" in names:
                                preferred = "bge-m3"
                            elif "nomic-embed-text" in names:
                                preferred = "nomic-embed-text"
            except Exception:
                pass
        if not preferred:
            preferred = "nomic-embed-text"

        ollama_embedding = await self.generate_ollama_embedding(
            text, model=preferred, is_query=is_query
        )
        if ollama_embedding:
            return ollama_embedding, preferred

        openai_embedding = await self.generate_openai_embedding(text)
        if openai_embedding:
            try:
                from backend.app.services.system_settings_store import (
                    SystemSettingsStore,
                )

                settings_store = SystemSettingsStore()
                embedding_setting = settings_store.get_setting("embedding_model")
                openai_model = (
                    str(embedding_setting.value)
                    if embedding_setting
                    else "text-embedding-3-small"
                )
            except Exception:
                openai_model = "text-embedding-3-small"
            return openai_embedding, openai_model

        return None, None

    def get_ollama_url(self) -> Optional[str]:
        """
        Return a reachable Ollama base URL, or None.

        Returns:
            Reachable Ollama URL if the tags endpoint responds.
        """
        import requests as requests_client

        candidates = []
        env_host = os.getenv("OLLAMA_HOST", "").strip()
        if env_host:
            candidates.append(env_host)
        candidates += [
            "http://host.docker.internal:11434",
            "http://ollama:11434",
        ]
        for url in candidates:
            try:
                response = requests_client.get(f"{url}/api/tags", timeout=2)
                if response.status_code == 200:
                    return url
            except Exception:
                continue
        return None

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
        try:
            import httpx

            ollama_url = os.getenv("OLLAMA_HOST", "").strip()
            if not ollama_url:
                ollama_url = "http://host.docker.internal:11434"

            embed_model = model or os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")

            prompt_text = text
            base_model = embed_model.split(":")[0].lower()
            if base_model in self._NOMIC_MODELS:
                prefix = "search_query" if is_query else "search_document"
                prompt_text = f"{prefix}: {text}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={"model": embed_model, "prompt": prompt_text},
                )

                if response.status_code == 200:
                    data = response.json()
                    embedding = data.get("embedding")
                    if embedding:
                        logger.debug(
                            "Generated Ollama embedding model=%s dim=%d",
                            embed_model,
                            len(embedding),
                        )
                        return embedding
                else:
                    logger.warning(
                        "Ollama embedding failed status=%d: %s",
                        response.status_code,
                        response.text[:200],
                    )

                if ollama_url == "http://host.docker.internal:11434":
                    response2 = await client.post(
                        "http://ollama:11434/api/embeddings",
                        json={"model": embed_model, "prompt": prompt_text},
                    )
                    if response2.status_code == 200:
                        embedding2 = response2.json().get("embedding")
                        if embedding2:
                            return embedding2

        except Exception as e:
            logger.warning("Ollama embedding unavailable: %s", e)

        return None

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
