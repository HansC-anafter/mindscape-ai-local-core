"""
Workspace Data Sources Indexing API

Provides endpoints for indexing workspace data sources into vector database.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
import logging

from backend.app.services.local_folder_indexer import LocalFolderIndexer
from backend.app.services.vector_search import VectorSearchService
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.dependencies.auth import (
    AuthContext,
    build_retrieval_access_context,
    get_current_user,
)
from backend.app.services.knowledge_authorization import RetrievalScopeDenied

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace-indexing"])


@router.post("/workspaces/{workspace_id}/data-sources/index")
async def index_workspace_data_sources(
    workspace_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    """
    Index workspace data sources into vector database

    Triggers indexing of configured local_folder and other data sources.

    Args:
        workspace_id: Workspace ID

    Returns:
        Dictionary with indexing results
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
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
            vector_service=vector_service,
            workspace_id=workspace_id,
            access_context=context,
        )

        result = await indexer.index_folder(local_folder)

        logger.info(f"Indexed workspace {workspace_id} data sources: {result}")
        return result

    except HTTPException:
        raise
    except (PermissionError, RetrievalScopeDenied) as e:
        raise HTTPException(
            status_code=403,
            detail="Knowledge access is not authorized for this workspace.",
        ) from e
    except Exception as e:
        logger.error(f"Failed to index workspace data sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Indexing failed.") from e


@router.get("/workspaces/{workspace_id}/data-sources/status")
async def get_workspace_data_sources_status(
    workspace_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    """
    Get indexing status for workspace data sources

    Args:
        workspace_id: Workspace ID

    Returns:
        Status dictionary with file counts and indexed chunks
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
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
            vector_service=vector_service,
            workspace_id=workspace_id,
            access_context=context,
        )

        status = await indexer.get_index_status(local_folder)
        return status

    except HTTPException:
        raise
    except (PermissionError, RetrievalScopeDenied) as e:
        raise HTTPException(
            status_code=403,
            detail="Knowledge access is not authorized for this workspace.",
        ) from e
    except Exception as e:
        logger.error(f"Failed to get data sources status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get status.") from e
