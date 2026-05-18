"""Shared state for sandbox route modules."""

from typing import Dict

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.sandbox.preview_server import SandboxPreviewServer
from backend.app.services.sandbox.sandbox_manager import SandboxManager

store = MindscapeStore()
sandbox_manager = SandboxManager(store)
_preview_servers: Dict[str, SandboxPreviewServer] = {}


def _get_preview_server_key(workspace_id: str, sandbox_id: str) -> str:
    """Generate unique key for preview server."""
    return f"{workspace_id}:{sandbox_id}"
