"""
Playbook Indexing API
Provides endpoints for indexing Playbooks to pgvector
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from backend.app.services.playbook_indexer import PlaybookIndexer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Playbook Indexing"])


# Request/Response Models
class IndexPlaybookRequest(BaseModel):
    playbook_code: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class IndexPlaybookResponse(BaseModel):
    playbook_code: str
    chunks_indexed: int
    success: bool
    message: str


class ReindexAllResponse(BaseModel):
    total_playbooks: int
    indexed_playbooks: int
    total_chunks: int
    failed: List[str]
    success: bool


# Playbook Indexing Endpoints

@router.post("/{playbook_code}/reindex", response_model=IndexPlaybookResponse)
async def reindex_playbook(
    playbook_code: str,
    request: IndexPlaybookRequest
):
    """
    Reindex a specific Playbook

    Example:
    ```json
    {
      "playbook_code": "project-breakdown",
      "content": "# Playbook content in markdown...",
      "metadata": {
        "version": "1.0.0",
        "agent_type": "planner",
        "tags": ["onboarding", "planning"]
      }
    }
    ```
    """
    try:
        indexer = PlaybookIndexer()

        chunk_count = await indexer.index_playbook(
            playbook_code=playbook_code,
            content=request.content,
            metadata=request.metadata
        )

        if chunk_count > 0:
            return IndexPlaybookResponse(
                playbook_code=playbook_code,
                chunks_indexed=chunk_count,
                success=True,
                message=f"Successfully indexed {chunk_count} chunks"
            )
        else:
            return IndexPlaybookResponse(
                playbook_code=playbook_code,
                chunks_indexed=0,
                success=False,
                message="Failed to index playbook (check logs for details)"
            )

    except Exception as e:
        logger.error(f"Failed to reindex playbook {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reindex-all", response_model=ReindexAllResponse)
async def reindex_all_playbooks(
    background_tasks: BackgroundTasks,
    playbooks_dir: str = Query("docs/playbooks", description="Playbooks directory path")
):
    """
    Reindex all Playbooks from the playbooks directory

    This operation runs in the background and may take a while.

    Example: POST /api/v1/playbooks/reindex-all?playbooks_dir=docs/playbooks
    """
    try:
        indexer = PlaybookIndexer()

        # Run indexing in background
        stats = await indexer.reindex_all_playbooks(playbooks_dir=playbooks_dir)

        return ReindexAllResponse(
            total_playbooks=stats["total_playbooks"],
            indexed_playbooks=stats["indexed_playbooks"],
            total_chunks=stats["total_chunks"],
            failed=stats["failed"],
            success=stats["indexed_playbooks"] > 0
        )

    except Exception as e:
        logger.error(f"Failed to reindex all playbooks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/chunks")
async def get_playbook_chunks(
    playbook_code: str,
    limit: int = Query(50, description="Maximum number of chunks to return")
):
    """
    Get all indexed chunks for a Playbook

    Example: GET /api/v1/playbooks/project-breakdown/chunks?limit=10
    """
    try:
        from app.services.playbook_indexer import PlaybookIndexer
        indexer = PlaybookIndexer()

        conn = indexer._get_connection()
        try:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute('''
                SELECT
                    id, section_type, content, metadata,
                    created_at, updated_at
                FROM playbook_knowledge
                WHERE playbook_code = %s
                ORDER BY (metadata->>'section_number')::int
                LIMIT %s
            ''', (playbook_code, limit))

            chunks = cursor.fetchall()
            return {
                "playbook_code": playbook_code,
                "total": len(chunks),
                "chunks": [dict(chunk) for chunk in chunks]
            }

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Failed to get chunks for {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{playbook_code}/chunks")
async def delete_playbook_chunks(playbook_code: str):
    """
    Delete all indexed chunks for a Playbook

    Example: DELETE /api/v1/playbooks/project-breakdown/chunks
    """
    try:
        from app.services.playbook_indexer import PlaybookIndexer
        indexer = PlaybookIndexer()

        indexer._delete_existing_chunks(playbook_code)

        return {
            "playbook_code": playbook_code,
            "success": True,
            "message": f"Deleted all chunks for {playbook_code}"
        }

    except Exception as e:
        logger.error(f"Failed to delete chunks for {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
