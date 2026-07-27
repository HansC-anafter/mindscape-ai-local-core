"""
WordPress Sync API
Provides endpoints for syncing WordPress content to pgvector
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
import logging

from backend.app.services.wordpress_sync import WordPressSync
from backend.app.dependencies.auth import (
    AuthContext,
    build_retrieval_access_context,
    get_current_user,
)
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)
from backend.app.services.knowledge_authorization import RetrievalScopeDenied

logger = logging.getLogger(__name__)

router = APIRouter(tags=["External Docs Sync"])


def _raise_external_docs_failure(operation: str, exc: Exception) -> None:
    if isinstance(exc, (PermissionError, RetrievalScopeDenied)):
        raise HTTPException(
            status_code=403,
            detail="Knowledge access is not authorized for this workspace.",
        ) from exc
    logger.error("%s: %s", operation, exc, exc_info=True)
    raise HTTPException(
        status_code=500,
        detail="External document operation failed.",
    ) from exc


# Request/Response Models
class WordPressSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=64)
    site_url: str
    post_types: Optional[List[str]] = None
    per_page: int = Field(default=10, ge=1, le=100)


class DocumentSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=64)
    source_app: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=256)
    title: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class WordPressSyncResponse(BaseModel):
    total_fetched: int
    new: int
    updated: int
    skipped: int
    failed: List[Dict[str, Any]]
    success: bool


# WordPress Sync Endpoints

@router.post("/sync/document")
async def sync_document(
    request: DocumentSyncRequest,
    auth: AuthContext = Depends(get_current_user),
):
    """
    Sync a single document (or chunk) to the vector database.
    Generates embedding automatically.
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(request.workspace_id,),
        )
        result = await AuthorizedLegacyDocumentFacade().replace_document(
            access_context=context,
            workspace_id=request.workspace_id,
            owner_capability_code="external_docs",
            source_app=request.source_app,
            source_id=request.source_id,
            doc_type="external_document",
            chunks=(
                LegacyDocumentChunk(
                    content=request.content,
                    title=request.title,
                    metadata=request.metadata or {},
                ),
            ),
        )
        return {
            "success": True,
            "source_id": request.source_id,
            "knowledge_resource_id": result.knowledge_resource_id,
            "projection_revision_id": result.projection_revision_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        _raise_external_docs_failure("Document sync failed", e)


@router.post("/sync/wordpress", response_model=WordPressSyncResponse)
async def sync_wordpress(
    request: WordPressSyncRequest,
    auth: AuthContext = Depends(get_current_user),
):
    """
    Sync WordPress posts and pages to vector database

    Example:
    ```json
    {
      "workspace_id": "workspace-1",
      "site_url": "https://example.com",
      "post_types": ["post", "page"],
      "per_page": 10
    }
    ```
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(request.workspace_id,),
        )
        sync_service = WordPressSync(
            workspace_id=request.workspace_id,
            access_context=context,
        )

        stats = await sync_service.sync_posts(
            site_url=request.site_url,
            post_types=request.post_types,
            per_page=request.per_page
        )

        return WordPressSyncResponse(
            total_fetched=stats["total_fetched"],
            new=stats["new"],
            updated=stats["updated"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            success=stats["new"] + stats["updated"] > 0
        )

    except Exception as e:
        _raise_external_docs_failure("WordPress sync failed", e)


@router.get("/wordpress/list")
async def list_wordpress_posts(
    workspace_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(100, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
):
    """
    List synced WordPress posts

    Example: GET /api/v1/external-docs/wordpress/list?limit=50
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
        sync_service = WordPressSync(
            workspace_id=workspace_id,
            access_context=context,
        )

        posts = await sync_service.list_synced_posts(
            limit=limit
        )

        return {
            "total": len(posts),
            "posts": posts
        }

    except Exception as e:
        _raise_external_docs_failure("Failed to list WordPress posts", e)


@router.delete("/wordpress/{source_id}")
async def delete_wordpress_post(
    source_id: str,
    workspace_id: str = Query(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_current_user),
):
    """
    Delete a synced WordPress post

    Example: DELETE /api/v1/external-docs/wordpress/wp_123?workspace_id=workspace-1
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
        sync_service = WordPressSync(
            workspace_id=workspace_id,
            access_context=context,
        )

        deleted = await sync_service.delete_post(
            source_id=source_id,
        )

        if deleted:
            return {
                "success": True,
                "message": f"Deleted post {source_id}"
            }
        else:
            raise HTTPException(status_code=404, detail="Post not found")

    except HTTPException:
        raise
    except Exception as e:
        _raise_external_docs_failure("Failed to delete WordPress post", e)


@router.get("/stats")
async def get_external_docs_stats(
    workspace_id: str = Query(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_current_user),
):
    """
    Get statistics about synced external documents

    Example: GET /api/v1/external-docs/stats
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
        return await asyncio.to_thread(
            AuthorizedLegacyDocumentFacade().document_stats,
            access_context=context,
            workspace_id=workspace_id,
        )

    except Exception as e:
        _raise_external_docs_failure("Failed to get external docs stats", e)
