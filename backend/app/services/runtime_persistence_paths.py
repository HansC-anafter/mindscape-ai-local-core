"""Shared runtime path helpers for workspace and model persistence."""

from __future__ import annotations

import os
from pathlib import Path


def _configured_path(env_name: str, legacy_suffix: str) -> Path:
    configured = str(os.getenv(env_name, "")).strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mindscape" / legacy_suffix


def get_workspace_storage_root() -> Path:
    """Return the canonical workspace storage root with a legacy fallback."""
    return _configured_path("WORKSPACE_STORAGE_ROOT", "workspaces")


def get_model_root() -> Path:
    """Return the canonical model cache root with a legacy fallback."""
    return _configured_path("MINDSCAPE_MODEL_ROOT", "models")
