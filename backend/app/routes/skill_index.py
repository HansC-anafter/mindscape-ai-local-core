"""
Skill Index API Routes

Provides endpoints for:
- Indexing SKILL.md files
- Searching capabilities by intent
- Listing all indexed capabilities
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from backend.app.services.skill_index_service import get_skill_index_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skill-index", tags=["skill-index"])


class IndexRequest(BaseModel):
    """Request to index capabilities"""

    directories: Optional[List[str]] = None
    force_reindex: bool = False


class IndexResponse(BaseModel):
    """Index operation response"""

    indexed: int
    skipped: int
    errors: int
    embeddings_generated: int = 0


class SearchRequest(BaseModel):
    """Capability search request"""

    query: str
    top_k: int = 5
    min_score: float = 0.3


class CapabilitySuggestion(BaseModel):
    """Suggested capability"""

    pack_code: str
    name: str
    description: str
    score: float
    skills: List[str]
    tools: List[str]


class SearchResponse(BaseModel):
    """Search results"""

    query: str
    suggestions: List[CapabilitySuggestion]


class CapabilityInfo(BaseModel):
    """Capability information"""

    pack_code: str
    name: str
    description: str
    skill_count: int
    tool_count: int
    categories: List[str]


@router.post("/index", response_model=IndexResponse)
async def index_capabilities(request: IndexRequest):
    """
    Index SKILL.md files from capability directories.

    Scans directories for SKILL.md files, parses them, and generates embeddings.
    """
    service = get_skill_index_service()

    try:
        stats = await service.index_capabilities(
            capabilities_dirs=request.directories,
            force_reindex=request.force_reindex,
        )

        embeddings_count = await service.generate_embeddings()

        return IndexResponse(
            indexed=stats["indexed"],
            skipped=stats["skipped"],
            errors=stats["errors"],
            embeddings_generated=embeddings_count,
        )

    except Exception as e:
        logger.error(f"Failed to index capabilities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_capabilities(request: SearchRequest):
    """
    Search for relevant capabilities by user intent.

    Uses semantic similarity to find best-matching capabilities.
    """
    service = get_skill_index_service()

    try:
        results = await service.search(
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
        )

        suggestions = [
            CapabilitySuggestion(
                pack_code=doc.pack_code,
                name=doc.name,
                description=doc.description,
                score=round(score, 3),
                skills=[s.get("skill", "") for s in doc.skills[:3]],
                tools=[t.get("tool", "") for t in doc.tools[:3]],
            )
            for doc, score in results
        ]

        return SearchResponse(query=request.query, suggestions=suggestions)

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capabilities", response_model=List[CapabilityInfo])
async def list_capabilities():
    """
    List all indexed capabilities.
    """
    service = get_skill_index_service()

    capabilities = service.list_all_capabilities()

    return [
        CapabilityInfo(
            pack_code=c["pack_code"],
            name=c["name"],
            description=c["description"],
            skill_count=c["skill_count"],
            tool_count=c["tool_count"],
            categories=c["categories"],
        )
        for c in capabilities
    ]


@router.get("/suggest")
async def suggest_capabilities(
    query: str = Query(..., description="User intent/query"),
    top_k: int = Query(5, description="Number of suggestions"),
):
    """
    Quick endpoint for capability suggestions (for PlanBuilder integration).
    """
    service = get_skill_index_service()

    # Ensure index is loaded
    if not service._skill_cache:
        await service.index_capabilities()

    return {"suggestions": service.get_capability_suggestions(query)}
