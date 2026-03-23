"""Model selection helpers for ToolEmbeddingService."""

from __future__ import annotations

import os
from typing import Callable, Mapping, Sequence

import requests

from .constants import DEFAULT_OLLAMA_CANDIDATES, EMBED_MODEL_KEYWORDS


def _get_ollama_candidates(env_host: str | None) -> list[str]:
    candidates: list[str] = []
    if env_host:
        candidates.append(env_host)
    candidates.extend(DEFAULT_OLLAMA_CANDIDATES)
    return candidates


def _extract_embed_models(
    models_payload: Sequence[Mapping[str, object]],
    keywords: Sequence[str] = EMBED_MODEL_KEYWORDS,
) -> list[str]:
    embed_models: list[str] = []
    for model in models_payload:
        name = str(model.get("name", "")).split(":")[0]
        if not name:
            continue
        if any(keyword in name.lower() for keyword in keywords):
            if name not in embed_models:
                embed_models.append(name)
    return embed_models


def discover_embed_models(
    *,
    requests_get: Callable[..., object] | None = None,
    env_host: str | None = None,
    timeout: float = 2.0,
) -> list[str]:
    """Discover available Ollama embedding models in priority order."""
    get = requests_get or requests.get
    for base_url in _get_ollama_candidates(env_host):
        try:
            response = get(f"{base_url}/api/tags", timeout=timeout)
            if getattr(response, "status_code", None) != 200:
                continue
            payload = response.json() or {}
            models = payload.get("models", [])
            return _extract_embed_models(models)
        except Exception:
            continue
    return []


def get_current_embedding_model(
    *,
    system_settings_store_cls=None,
    requests_get: Callable[..., object] | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the active embedding model used by ToolEmbeddingService."""
    env = environ or os.environ
    store_cls = system_settings_store_cls
    if store_cls is None:
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store_cls = SystemSettingsStore
        except Exception:
            store_cls = None

    if store_cls is not None:
        try:
            store = store_cls()
            frontend_setting = store.get_setting("ollama_embed_model")
            if frontend_setting and frontend_setting.value:
                value = str(frontend_setting.value).strip()
                if value:
                    return value
        except Exception:
            pass

    preferred = env.get("OLLAMA_EMBED_MODEL", "").strip()
    embed_models = discover_embed_models(
        requests_get=requests_get,
        env_host=env.get("OLLAMA_HOST", "").strip() or None,
    )
    if embed_models:
        if preferred:
            return preferred
        if "bge-m3" in embed_models:
            return "bge-m3"
        if "nomic-embed-text" in embed_models:
            return "nomic-embed-text"

    if store_cls is not None:
        try:
            store = store_cls()
            setting = store.get_setting("embedding_model")
            if setting and setting.value:
                return str(setting.value)
        except Exception:
            pass

    return "text-embedding-3-small"
