"""
Tool RAG Search endpoint.

Enables per-task tool filtering by searching tool embeddings
and returning matching pack codes for MCP gateway whitelist.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class RagSearchRequest(BaseModel):
    query: str = Field(..., description="Task prompt to search relevant tools for")
    top_k: int = Field(default=30, ge=1, le=100, description="Max tools to return")
    min_score: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Minimum similarity threshold"
    )


class RagSearchResponse(BaseModel):
    tool_ids: list[str]
    pack_codes: list[str]
    status: str = Field(description="hit | miss | error")
    match_count: int = 0


@router.post("/rag-search/", response_model=RagSearchResponse)
async def rag_search(body: RagSearchRequest):
    """Search tool embeddings to find relevant packs for a task prompt."""
    try:
        from backend.app.services.tool_embedding_service import ToolEmbeddingService

        svc = ToolEmbeddingService()
        matches, rag_status = await svc.search(
            query=body.query,
            top_k=body.top_k,
            min_score=body.min_score,
        )

        tool_ids = [m.tool_id for m in matches]
        pack_codes = sorted({m.capability_code for m in matches if m.capability_code})

        logger.info(
            f"RAG search: query='{body.query[:60]}', "
            f"matches={len(matches)}, packs={pack_codes}, status={rag_status}"
        )

        return RagSearchResponse(
            tool_ids=tool_ids,
            pack_codes=pack_codes,
            status=rag_status,
            match_count=len(matches),
        )
    except Exception as e:
        logger.error(f"RAG search endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
