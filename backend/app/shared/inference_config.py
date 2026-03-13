"""
Dynamic inference configuration reader.

Reads max_output_tokens from model metadata (set by UI slider),
falling back to heuristic defaults based on model characteristics.

Architecture:
  model.metadata.max_output_tokens  (UI slider)
    → InferenceConfig.get_max_tokens()
      → call_llm / stream_* / _route_mlx
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Heuristic defaults by model name pattern
_HEURISTIC_DEFAULTS = {
    "gpt-5": 8000,
    "o1": 8000,
    "o3": 8000,
    "gemini": 8192,
    "qwen": 16384,      # thinking model — needs space for CoT
    "llama": 8192,
    "claude": 8192,
    "mistral": 8192,
}
_DEFAULT_MAX_TOKENS = 4096

# Module-level cache to avoid DB hit on every inference call
_cache: dict = {"data": {}, "ts": 0}
_CACHE_TTL = 60  # seconds


class InferenceConfig:
    """Resolve max_output_tokens for a given model."""

    @staticmethod
    def get_max_tokens(
        model_name: str,
        caller_default: Optional[int] = None,
    ) -> int:
        """Return max_output_tokens for the model.

        Priority:
          1. model.metadata.max_output_tokens  (user slider setting)
          2. caller_default  (from the call site, if any)
          3. Heuristic by model name pattern
          4. Global _DEFAULT_MAX_TOKENS (4096)
        """
        if not model_name:
            return caller_default or _DEFAULT_MAX_TOKENS

        # Priority 1: Model metadata from DB (cached)
        user_setting = _read_metadata_max_tokens(model_name)
        if user_setting is not None:
            logger.debug(
                "InferenceConfig: metadata max_output_tokens=%d for %s",
                user_setting, model_name,
            )
            return user_setting

        # Priority 2: Caller-provided default
        if caller_default is not None:
            return caller_default

        # Priority 3: Heuristic by model name
        name_lower = model_name.lower()
        for pattern, default in _HEURISTIC_DEFAULTS.items():
            if pattern in name_lower:
                return default

        return _DEFAULT_MAX_TOKENS


def _read_metadata_max_tokens(model_name: str) -> Optional[int]:
    """Read max_output_tokens from model_configs.metadata (with TTL cache)."""
    global _cache

    now = time.time()

    # Refresh cache if stale
    if now - _cache["ts"] > _CACHE_TTL:
        try:
            from backend.app.services.model_config_store import ModelConfigStore
            store = ModelConfigStore()
            models = store.get_all_models(enabled=True)
            new_data = {}
            for m in models:
                if m.metadata and m.metadata.get("max_output_tokens") is not None:
                    new_data[m.model_name] = int(m.metadata["max_output_tokens"])
            _cache = {"data": new_data, "ts": now}
        except Exception as e:
            logger.debug("InferenceConfig: cache refresh failed: %s", e)
            # Keep stale cache if refresh fails
            if not _cache["data"]:
                _cache["ts"] = now  # prevent retry storm

    return _cache["data"].get(model_name)
