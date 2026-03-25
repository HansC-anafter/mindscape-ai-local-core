"""
Hugging Face auth resolution shared across download surfaces.

This keeps a single source of truth for resolving HF credentials while still
allowing environment or cached-login fallback outside system settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_HF_TOKEN_ENV_KEYS = (
    "HF_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)


@dataclass(frozen=True)
class HuggingFaceAuthResolution:
    token: Optional[str]
    source: str = "none"

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def authorization_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}


def _clean_token(raw: object) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    token = raw.strip()
    return token or None


def _resolve_from_system_settings(settings_store=None) -> Optional[HuggingFaceAuthResolution]:
    try:
        if settings_store is None:
            from backend.app.services.system_settings_store import SystemSettingsStore

            settings_store = SystemSettingsStore()
        setting = settings_store.get_setting("huggingface_api_key")
        token = _clean_token(setting.value if setting else None)
        if token:
            return HuggingFaceAuthResolution(
                token=token,
                source="system_settings:huggingface_api_key",
            )
    except Exception as exc:
        logger.debug("Failed to resolve HF auth from system settings: %s", exc)
    return None


def _resolve_from_env() -> Optional[HuggingFaceAuthResolution]:
    for env_key in _HF_TOKEN_ENV_KEYS:
        token = _clean_token(os.getenv(env_key))
        if token:
            return HuggingFaceAuthResolution(token=token, source=f"env:{env_key}")
    return None


def _resolve_from_hub_cache() -> Optional[HuggingFaceAuthResolution]:
    try:
        from huggingface_hub import get_token

        token = _clean_token(get_token())
        if token:
            return HuggingFaceAuthResolution(
                token=token,
                source="huggingface_hub:get_token",
            )
    except Exception as exc:
        logger.debug("Failed to resolve HF auth from huggingface_hub: %s", exc)

    token_file = Path("~/.cache/huggingface/token").expanduser()
    try:
        token = _clean_token(token_file.read_text(encoding="utf-8"))
        if token:
            return HuggingFaceAuthResolution(
                token=token,
                source=f"cache_file:{token_file}",
            )
    except Exception:
        pass

    return None


def resolve_huggingface_auth(settings_store=None) -> HuggingFaceAuthResolution:
    resolved = _resolve_from_system_settings(settings_store=settings_store)
    if resolved and resolved.configured:
        return resolved
    for resolver in (_resolve_from_env, _resolve_from_hub_cache):
        fallback = resolver()
        if fallback and fallback.configured:
            return fallback
    return HuggingFaceAuthResolution(token=None, source="none")
