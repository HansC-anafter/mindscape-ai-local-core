"""Resolve chat model names for conversation pipeline callers."""

from __future__ import annotations

from typing import Any, Optional

from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model


def resolve_conversational_model_name(
    requested_model_name: Optional[str] = None,
    *,
    workspace: Optional[Any] = None,
    db_path: Optional[str] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """Return the explicit request model or the configured system chat model.

    The workspace and db_path parameters are accepted for compatibility with
    callers that may later add scoped model selection.
    """
    del workspace, db_path, default

    if requested_model_name and requested_model_name.strip():
        return requested_model_name.strip()

    return get_model_name_from_chat_model()
