"""
Workspace Data Sources Indexing API

Provides endpoints for indexing workspace data sources into vector database.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from backend.app.services.local_folder_indexer import LocalFolderIndexer
from backend.app.services.vector_search import VectorSearchService
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace-indexing"])


@router.post("/workspaces/{workspace_id}/data-sources/index")
async def index_workspace_data_sources(
    workspace_id: str,
    user_id: str = Query("system", description="User ID for indexing"),
):
    """
    Index workspace data sources into vector database

    Triggers indexing of configured local_folder and other data sources.

    Args:
        workspace_id: Workspace ID
        user_id: User ID for indexing

    Returns:
        Dictionary with indexing results
    """
    try:
        # Get workspace to check data_sources config
        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace not found: {workspace_id}"
            )

        data_sources = workspace.data_sources or {}
        local_folder = data_sources.get("local_folder")

        if not local_folder:
            return {
                "success": False,
                "message": "No local_folder configured in workspace data_sources",
                "workspace_id": workspace_id,
                "data_sources": data_sources,
            }

        # Initialize indexer and run
        vector_service = VectorSearchService()
        indexer = LocalFolderIndexer(
            vector_service=vector_service, workspace_id=workspace_id
        )

        result = await indexer.index_folder(local_folder, user_id=user_id)

        logger.info(f"Indexed workspace {workspace_id} data sources: {result}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to index workspace data sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/workspaces/{workspace_id}/data-sources/status")
async def get_workspace_data_sources_status(
    workspace_id: str,
    user_id: str = Query("system", description="User ID"),
):
    """
    Get indexing status for workspace data sources

    Args:
        workspace_id: Workspace ID
        user_id: User ID

    Returns:
        Status dictionary with file counts and indexed chunks
    """
    try:
        # Get workspace
        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace not found: {workspace_id}"
            )

        data_sources = workspace.data_sources or {}
        local_folder = data_sources.get("local_folder")

        if not local_folder:
            return {
                "local_folder": None,
                "message": "No local_folder configured",
                "workspace_id": workspace_id,
            }

        # Get status
        vector_service = VectorSearchService()
        indexer = LocalFolderIndexer(
            vector_service=vector_service, workspace_id=workspace_id
        )

        status = await indexer.get_index_status(local_folder, user_id=user_id)
        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get data sources status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
