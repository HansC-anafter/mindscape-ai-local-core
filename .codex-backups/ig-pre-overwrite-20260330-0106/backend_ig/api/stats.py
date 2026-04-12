"""
IG Stats API

Provides statistics for IG capability, including saved account counts.
"""

import logging
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ig/stats", tags=["IG Stats"])


class SavedCountResponse(BaseModel):
    """Response model for saved count query"""

    execution_id: Optional[str] = None
    seed: Optional[str] = None
    count: int


@router.get("/saved-count")
async def get_saved_count(
    workspace_id: str = Query(..., description="Workspace ID"),
    execution_id: Optional[str] = Query(None, description="Filter by execution ID"),
    seed: Optional[str] = Query(None, description="Filter by seed (target_username)"),
) -> SavedCountResponse:
    """
    Get count of saved accounts in ig_accounts_flat table.

    Useful for showing real-time persistence progress during execution.
    """
    from sqlalchemy import text
    from app.database.engine import engine_postgres_core

    try:
        with engine_postgres_core.connect() as conn:
            # Build query based on filters
            conditions = ["workspace_id = :workspace_id"]
            params = {"workspace_id": workspace_id}

            if execution_id:
                conditions.append("execution_id = :execution_id")
                params["execution_id"] = execution_id

            if seed:
                conditions.append("seed = :seed")
                params["seed"] = seed

            where_clause = " AND ".join(conditions)
            query = text(
                "SELECT COUNT(*) as cnt FROM ig_accounts_flat "
                f"WHERE {where_clause} AND handle NOT LIKE '__seed_placeholder__%'"
            )

            result = conn.execute(query, params)
            row = result.fetchone()
            count = row[0] if row else 0

            return SavedCountResponse(
                execution_id=execution_id,
                seed=seed,
                count=count,
            )
    except Exception as e:
        logger.error(f"[IG Stats] Failed to query saved count: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query saved count: {e}")
