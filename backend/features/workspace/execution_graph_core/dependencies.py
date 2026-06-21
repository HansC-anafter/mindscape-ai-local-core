"""Dependencies for execution graph routes."""

from fastapi import Depends

from backend.app.routes.workspace_dependencies import get_store
from backend.app.services.mindscape_graph_service import MindscapeGraphService
from backend.app.services.mindscape_store import MindscapeStore


def get_graph_service(
    store: MindscapeStore = Depends(get_store),
) -> MindscapeGraphService:
    """Get a Mindscape graph service instance."""
    return MindscapeGraphService(db_path=store.db_path)
