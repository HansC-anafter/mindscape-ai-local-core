
from backend.app.services.stores.control_profile_store import ControlProfileStore
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)

from .state import store


def get_runtime_profile_store() -> WorkspaceRuntimeProfileStore:
    """Get runtime profile store instance."""
    return WorkspaceRuntimeProfileStore()


def get_control_profile_store() -> ControlProfileStore:
    """Get control profile store instance."""
    return ControlProfileStore(store.db_path)
