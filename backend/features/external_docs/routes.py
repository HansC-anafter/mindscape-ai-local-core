"""
WordPress Sync API
Provides endpoints for syncing WordPress content to pgvector
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from backend.app.services.wordpress_sync import WordPressSync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["External Docs Sync"])


# Request/Response Models
class WordPressSyncRequest(BaseModel):
    site_url: str
    user_id: str = "default_user"
    post_types: Optional[List[str]] = None
    per_page: int = 10


class WordPressSyncResponse(BaseModel):
    total_fetched: int
    new: int
    updated: int
    skipped: int
    failed: List[Dict[str, Any]]
    success: bool


# WordPress Sync Endpoints

@router.post("/sync/wordpress", response_model=WordPressSyncResponse)
async def sync_wordpress(
    request: WordPressSyncRequest,
    background_tasks: BackgroundTasks
):
    """
    Sync WordPress posts and pages to vector database

    Example:
    ```json
    {
      "site_url": "https://example.com",
      "user_id": "default_user",
      "post_types": ["post", "page"],
      "per_page": 10
    }
    ```
    """
    try:
        sync_service = WordPressSync()

        stats = await sync_service.sync_posts(
            site_url=request.site_url,
            user_id=request.user_id,
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
        logger.error(f"WordPress sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wordpress/list")
async def list_wordpress_posts(
    user_id: str = Query("default_user", description="User ID"),
    limit: int = Query(100, description="Maximum number of posts")
):
    """
    List synced WordPress posts

    Example: GET /api/v1/external-docs/wordpress/list?limit=50
    """
    try:
        sync_service = WordPressSync()

        posts = await sync_service.list_synced_posts(
            user_id=user_id,
            limit=limit
        )

        return {
            "total": len(posts),
            "posts": posts
        }

    except Exception as e:
        logger.error(f"Failed to list WordPress posts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/wordpress/{source_id}")
async def delete_wordpress_post(
    source_id: str,
    user_id: str = Query("default_user", description="User ID")
):
    """
    Delete a synced WordPress post

    Example: DELETE /api/v1/external-docs/wordpress/wp_123?user_id=default_user
    """
    try:
        sync_service = WordPressSync()

        deleted = await sync_service.delete_post(
            source_id=source_id,
            user_id=user_id
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
        logger.error(f"Failed to delete WordPress post: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_external_docs_stats(
    user_id: str = Query("default_user", description="User ID")
):
    """
    Get statistics about synced external documents

    Example: GET /api/v1/external-docs/stats
    """
    try:
        from app.services.wordpress_sync import WordPressSync
        sync_service = WordPressSync()

        conn = sync_service._get_connection()
        try:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get counts by source_app
            cursor.execute('''
                SELECT
                    source_app,
                    doc_type,
                    COUNT(*) as count
                FROM external_docs
                WHERE user_id = %s
                GROUP BY source_app, doc_type
                ORDER BY source_app, doc_type
            ''', (user_id,))

            counts = cursor.fetchall()

            # Get total count
            cursor.execute('''
                SELECT COUNT(*) as total
                FROM external_docs
                WHERE user_id = %s
            ''', (user_id,))

            total_row = cursor.fetchone()
            total = total_row['total'] if total_row else 0

            # Get recent syncs
            cursor.execute('''
                SELECT
                    source_app,
                    source_id,
                    title,
                    last_synced_at
                FROM external_docs
                WHERE user_id = %s
                ORDER BY last_synced_at DESC
                LIMIT 10
            ''', (user_id,))

            recent = cursor.fetchall()

            return {
                "total": total,
                "by_source": [dict(c) for c in counts],
                "recent_syncs": [dict(r) for r in recent]
            }

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Failed to get external docs stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
