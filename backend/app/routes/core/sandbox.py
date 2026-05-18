"""Compatibility facade for sandbox routes."""

from .sandbox_core.crud_routes import (
    create_sandbox,
    delete_sandbox,
    get_sandbox,
    list_sandboxes,
)
from .sandbox_core.file_routes import get_file_content, list_files
from .sandbox_core.port_routes import cleanup_stale_ports, get_port_manager_status
from .sandbox_core.preview_routes import (
    ensure_preview_ready,
    get_preview_server_status,
    start_preview_server,
    stop_preview_server,
)
from .sandbox_core.project_routes import get_sandbox_by_project
from .sandbox_core.router import router
from .sandbox_core.schemas import (
    CreateSandboxRequest,
    CreateVersionRequest,
    EnsurePreviewRequest,
    StartPreviewRequest,
    SyncToWorkspaceRequest,
)
from .sandbox_core.state import (
    _get_preview_server_key,
    _preview_servers,
    sandbox_manager,
    store,
)
from .sandbox_core.sync_routes import get_sync_diff, sync_sandbox_to_workspace
from .sandbox_core.version_routes import (
    create_version,
    get_version_metadata,
    list_versions,
)

__all__ = [
    "router",
    "store",
    "sandbox_manager",
    "_preview_servers",
    "CreateSandboxRequest",
    "CreateVersionRequest",
    "StartPreviewRequest",
    "EnsurePreviewRequest",
    "SyncToWorkspaceRequest",
    "list_sandboxes",
    "create_sandbox",
    "get_sandbox",
    "delete_sandbox",
    "list_files",
    "get_file_content",
    "create_version",
    "list_versions",
    "get_version_metadata",
    "get_sandbox_by_project",
    "ensure_preview_ready",
    "_get_preview_server_key",
    "start_preview_server",
    "stop_preview_server",
    "get_sync_diff",
    "sync_sandbox_to_workspace",
    "get_preview_server_status",
    "get_port_manager_status",
    "cleanup_stale_ports",
]
