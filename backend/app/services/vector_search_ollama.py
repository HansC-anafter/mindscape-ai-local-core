"""Bounded Ollama embedding provider client for vector search."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import os
from typing import Any, Iterable
from urllib.parse import urlsplit

import httpx
import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OllamaEmbeddingOutcome:
    """Typed internal result; public receipts must omit embedding content."""

    embedding: tuple[float, ...] = ()
    model: str = ""
    base_url: str = ""
    error_code: str | None = None
    error_detail: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.embedding) and self.error_code is None

    @property
    def dimension(self) -> int:
        return len(self.embedding)


class OllamaEmbeddingClient:
    """Own Ollama URL discovery and the canonical ``/api/embed`` contract."""

    _NOMIC_MODELS = {"nomic-embed-text", "nomic-embed-text-v1.5"}
    _MODEL_PRIORITY = ("bge-m3", "nomic-embed-text")
    _DISCOVERY_TIMEOUT_SECONDS = 3.0
    _CONNECT_TIMEOUT_SECONDS = 3.0
    _READ_TIMEOUT_SECONDS = 60.0
    _WRITE_TIMEOUT_SECONDS = 10.0

    def candidate_base_urls(self) -> tuple[str, ...]:
        """Return ordered, normalized, duplicate-free provider endpoints."""

        candidates = (
            os.getenv("OLLAMA_HOST", "").strip(),
            os.getenv("OLLAMA_BASE_URL", "").strip(),
            "http://host.docker.internal:11434",
            "http://ollama:11434",
        )
        return tuple(
            self._deduplicate(url.rstrip("/") for url in candidates if url)
        )

    def get_reachable_base_url(self) -> str | None:
        """Return the first endpoint whose tags route answers successfully."""

        for base_url in self.candidate_base_urls():
            try:
                response = requests.get(
                    f"{base_url}/api/tags",
                    timeout=2.0,
                )
                if response.status_code == 200:
                    return base_url
            except requests.RequestException:
                continue
        return None

    async def select_embedding_model(self, preferred: str = "") -> str:
        """Resolve the configured or best installed embedding model."""

        preferred = preferred.strip()
        if preferred:
            return preferred

        timeout = httpx.Timeout(self._DISCOVERY_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for base_url in self.candidate_base_urls():
                try:
                    response = await client.get(f"{base_url}/api/tags")
                except httpx.HTTPError:
                    continue
                if response.status_code != 200:
                    continue
                names = self._installed_base_model_names(response)
                for model_name in self._MODEL_PRIORITY:
                    if model_name in names:
                        return model_name
        return "nomic-embed-text"

    async def embed(
        self,
        text: str,
        *,
        model: str,
        is_query: bool,
    ) -> OllamaEmbeddingOutcome:
        """Generate one embedding without retrying ambiguous provider work."""

        prompt_text = self._provider_text(
            text,
            model=model,
            is_query=is_query,
        )
        timeout = httpx.Timeout(
            self._READ_TIMEOUT_SECONDS,
            connect=self._CONNECT_TIMEOUT_SECONDS,
            write=self._WRITE_TIMEOUT_SECONDS,
            pool=self._CONNECT_TIMEOUT_SECONDS,
        )
        last_connect_failure: OllamaEmbeddingOutcome | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for base_url in self.candidate_base_urls():
                endpoint = f"{base_url}/api/embed"
                try:
                    response = await client.post(
                        endpoint,
                        json={"model": model, "input": prompt_text},
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_connect_failure = self._failure(
                        code="connect_unavailable",
                        model=model,
                        base_url=base_url,
                        detail=type(exc).__name__,
                    )
                    continue
                except httpx.ReadTimeout as exc:
                    return self._failure(
                        code="read_timeout",
                        model=model,
                        base_url=base_url,
                        detail=type(exc).__name__,
                    )
                except httpx.TimeoutException as exc:
                    return self._failure(
                        code="request_timeout",
                        model=model,
                        base_url=base_url,
                        detail=type(exc).__name__,
                    )
                except httpx.HTTPError as exc:
                    return self._failure(
                        code="transport_error",
                        model=model,
                        base_url=base_url,
                        detail=type(exc).__name__,
                    )

                if response.status_code != 200:
                    return self._failure(
                        code=f"http_{response.status_code}",
                        model=model,
                        base_url=base_url,
                        detail=response.text[:160],
                    )
                try:
                    payload = response.json()
                except ValueError as exc:
                    return self._failure(
                        code="invalid_json",
                        model=model,
                        base_url=base_url,
                        detail=type(exc).__name__,
                    )
                embedding = self._validated_embedding(payload)
                if embedding is None:
                    return self._failure(
                        code="invalid_embedding_shape",
                        model=model,
                        base_url=base_url,
                        detail="expected_one_non_empty_finite_vector",
                    )
                resolved_model = str(payload.get("model") or model)
                return OllamaEmbeddingOutcome(
                    embedding=embedding,
                    model=resolved_model,
                    base_url=base_url,
                )

        return last_connect_failure or self._failure(
            code="endpoint_unavailable",
            model=model,
            base_url="",
            detail="no_candidate_endpoint",
        )

    @classmethod
    def _provider_text(
        cls,
        text: str,
        *,
        model: str,
        is_query: bool,
    ) -> str:
        base_model = model.split(":")[0].lower()
        if base_model not in cls._NOMIC_MODELS:
            return text
        prefix = "search_query" if is_query else "search_document"
        return f"{prefix}: {text}"

    @staticmethod
    def _installed_base_model_names(response: httpx.Response) -> set[str]:
        try:
            models = response.json().get("models", [])
        except (AttributeError, ValueError):
            return set()
        return {
            str(model.get("name") or "").split(":")[0]
            for model in models
            if isinstance(model, dict) and model.get("name")
        }

    @staticmethod
    def _validated_embedding(payload: Any) -> tuple[float, ...] | None:
        if not isinstance(payload, dict):
            return None
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            return None
        candidate = embeddings[0]
        if not isinstance(candidate, list) or not candidate:
            return None
        try:
            embedding = tuple(float(value) for value in candidate)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in embedding):
            return None
        return embedding

    @staticmethod
    def _deduplicate(values: Iterable[str]) -> Iterable[str]:
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                yield value

    @staticmethod
    def _failure(
        *,
        code: str,
        model: str,
        base_url: str,
        detail: str,
    ) -> OllamaEmbeddingOutcome:
        safe_detail = detail.replace("\r", " ").replace("\n", " ")[:160]
        safe_endpoint = urlsplit(base_url).netloc.rsplit("@", 1)[-1]
        logger.warning(
            "ollama_embedding_failed code=%s model=%s endpoint=%s detail=%s",
            code,
            model,
            safe_endpoint,
            safe_detail,
        )
        return OllamaEmbeddingOutcome(
            model=model,
            base_url=base_url,
            error_code=code,
            error_detail=safe_detail,
        )
