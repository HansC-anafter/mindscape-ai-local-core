"""
Content Vault Indexing API

Provides endpoints for indexing Content Vault documents into vector database.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pathlib import Path
import logging
import os

from backend.app.services.content_vault_indexer import ContentVaultIndexer
from backend.app.services.vector_search import VectorSearchService
from backend.app.dependencies.auth import (
    AuthContext,
    build_retrieval_access_context,
    get_current_user,
)
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
)
from backend.app.services.knowledge_authorization import RetrievalScopeDenied

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/content-vault", tags=["content-vault"])


@router.post("/index")
async def index_vault(
    workspace_id: str = Query(..., min_length=1, max_length=64),
    vault_path: Optional[str] = Query(None, description="Path to content vault (defaults to CONTENT_VAULT_PATH env var)"),
    series_id: Optional[str] = Query(None, description="Specific series ID to index (if not provided, indexes all series)"),
    auth: AuthContext = Depends(get_current_user),
):
    """
    Index Content Vault documents into vector database

    Args:
        vault_path: Path to content vault (defaults to CONTENT_VAULT_PATH)
        series_id: Specific series ID to index (optional)

    Returns:
        Dictionary with indexing results
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH")
            if not vault_path:
                vault_path = str(Path.home() / "content-vault")

        vector_service = VectorSearchService()
        indexer = ContentVaultIndexer(
            vector_service,
            workspace_id=workspace_id,
            access_context=context,
        )

        if series_id:
            result = await indexer.index_series(vault_path, series_id)
        else:
            result = await indexer.index_all_series(vault_path)

        return result

    except (PermissionError, RetrievalScopeDenied) as e:
        raise HTTPException(
            status_code=403,
            detail="Knowledge access is not authorized for this workspace.",
        ) from e
    except Exception as e:
        logger.error(f"Failed to index vault: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Indexing failed.") from e


@router.get("/index/status")
async def get_index_status(
    workspace_id: str = Query(..., min_length=1, max_length=64),
    vault_path: Optional[str] = Query(None, description="Path to content vault"),
    auth: AuthContext = Depends(get_current_user),
):
    """
    Get indexing status for Content Vault

    Returns:
        Dictionary with indexing status information
    """
    try:
        context = await asyncio.to_thread(
            build_retrieval_access_context,
            auth,
            requested_workspace_ids=(workspace_id,),
        )
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH")
            if not vault_path:
                vault_path = str(Path.home() / "content-vault")

        from pathlib import Path
        vault_path_obj = Path(vault_path).expanduser().resolve()

        series_dir = vault_path_obj / "series"
        series_count = len(list(series_dir.glob("*.md"))) if series_dir.exists() else 0

        posts_dir = vault_path_obj / "posts" / "instagram"
        posts_count = len(list(posts_dir.glob("*.md"))) if posts_dir.exists() else 0

        documents = await asyncio.to_thread(
            AuthorizedLegacyDocumentFacade().list_documents,
            access_context=context,
            workspace_id=workspace_id,
            owner_capability_code="content_vault",
            source_app="content-vault",
            limit=200,
        )
        indexed_count = sum(
            int(document["chunk_count"]) for document in documents
        )

        return {
            'vault_path': str(vault_path),
            'series_count': series_count,
            'posts_count': posts_count,
            'indexed_documents': indexed_count,
            'indexed_percentage': round((indexed_count / max(posts_count, 1)) * 100, 2) if posts_count > 0 else 0
        }

    except (PermissionError, RetrievalScopeDenied) as e:
        raise HTTPException(
            status_code=403,
            detail="Knowledge access is not authorized for this workspace.",
        ) from e
    except Exception as e:
        logger.error(f"Failed to get index status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get status.") from e
