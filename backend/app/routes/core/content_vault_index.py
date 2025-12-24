"""
Content Vault Indexing API

Provides endpoints for indexing Content Vault documents into vector database.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pathlib import Path
import logging
import os

from backend.app.services.content_vault_indexer import ContentVaultIndexer
from backend.app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/content-vault", tags=["content-vault"])


@router.post("/index")
async def index_vault(
    vault_path: Optional[str] = Query(None, description="Path to content vault (defaults to CONTENT_VAULT_PATH env var)"),
    series_id: Optional[str] = Query(None, description="Specific series ID to index (if not provided, indexes all series)"),
    user_id: str = Query("system", description="User ID for indexing"),
):
    """
    Index Content Vault documents into vector database

    Args:
        vault_path: Path to content vault (defaults to CONTENT_VAULT_PATH)
        series_id: Specific series ID to index (optional)
        user_id: User ID for indexing

    Returns:
        Dictionary with indexing results
    """
    try:
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH")
            if not vault_path:
                vault_path = str(Path.home() / "content-vault")

        vector_service = VectorSearchService()
        indexer = ContentVaultIndexer(vector_service)

        if series_id:
            result = await indexer.index_series(vault_path, series_id, user_id)
        else:
            result = await indexer.index_all_series(vault_path, user_id)

        return result

    except Exception as e:
        logger.error(f"Failed to index vault: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/index/status")
async def get_index_status(
    vault_path: Optional[str] = Query(None, description="Path to content vault"),
    user_id: str = Query("system", description="User ID"),
):
    """
    Get indexing status for Content Vault

    Returns:
        Dictionary with indexing status information
    """
    try:
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH")
            if not vault_path:
                vault_path = str(Path.home() / "content-vault")

        vector_service = VectorSearchService()

        from pathlib import Path
        vault_path_obj = Path(vault_path).expanduser().resolve()

        series_dir = vault_path_obj / "series"
        series_count = len(list(series_dir.glob("*.md"))) if series_dir.exists() else 0

        posts_dir = vault_path_obj / "posts" / "instagram"
        posts_count = len(list(posts_dir.glob("*.md"))) if posts_dir.exists() else 0

        conn = vector_service._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM external_docs
                WHERE user_id = %s AND source_app = 'content-vault'
                """,
                (user_id,)
            )
            indexed_count = cursor.fetchone()[0]
        finally:
            conn.close()

        return {
            'vault_path': str(vault_path),
            'series_count': series_count,
            'posts_count': posts_count,
            'indexed_documents': indexed_count,
            'indexed_percentage': round((indexed_count / max(posts_count, 1)) * 100, 2) if posts_count > 0 else 0
        }

    except Exception as e:
        logger.error(f"Failed to get index status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

