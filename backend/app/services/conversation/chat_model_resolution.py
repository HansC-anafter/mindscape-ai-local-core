"""Shared conversational model resolution helpers.

Priority:
1. Explicit request/model override
2. Workspace metadata preferred_chat_model
3. Global system setting chat_model
"""

from typing import Any, Optional

from backend.app.services.system_settings_store import SystemSettingsStore


def resolve_workspace_preferred_chat_model(
    workspace: Optional[Any],
) -> Optional[str]:
    """Return workspace-scoped preferred chat model_name if present."""
    if not workspace:
        return None

    metadata = getattr(workspace, "metadata", None) or {}
    if not isinstance(metadata, dict):
        return None

    preferred = metadata.get("preferred_chat_model")
    if not isinstance(preferred, dict):
        return None

    model_name = preferred.get("model_name")
    if model_name and str(model_name).strip():
        return str(model_name).strip()
    return None


def resolve_conversational_model_name(
    explicit_model_name: Optional[str] = None,
    *,
    workspace: Optional[Any] = None,
    db_path: Optional[str] = None,
) -> Optional[str]:
    """Resolve model name for chat/meeting surfaces."""
    if explicit_model_name and str(explicit_model_name).strip():
        return str(explicit_model_name).strip()

    workspace_model_name = resolve_workspace_preferred_chat_model(workspace)
    if workspace_model_name:
        return workspace_model_name

    settings_store = SystemSettingsStore(db_path=db_path)
    chat_setting = settings_store.get_setting("chat_model")
    if chat_setting and chat_setting.value and str(chat_setting.value).strip():
        return str(chat_setting.value).strip()
    return None
