"""Mindscape seed, suggestion, and current-mode route group."""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Path, Query

from backend.app.models.mindscape import IntentCard, IntentStatus, PriorityLevel
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
from backend.features.mindscape.route_state import store

router = APIRouter()


@router.post("/seeds/extract")
async def extract_seeds(
    user_id: str = Query(..., description="Profile ID"),
    source_type: str = Query(
        ..., description="Source type: execution, conversation, tool_call"
    ),
    source_id: Optional[str] = Query(None, description="Source ID"),
    content: str = Query(..., description="Content to extract seeds from"),
):
    """Extract seeds from content (called automatically after executions)"""
    try:
        from ...capabilities.semantic_seeds.services.seed_extractor import SeedExtractor
        from backend.app.services.agent_runner import AgentRunner

        agent_runner = AgentRunner()
        try:
            llm_provider = get_llm_provider_from_settings(agent_runner.llm_manager)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"LLM provider not configured: {e}"
            )

        extractor = SeedExtractor(llm_provider=llm_provider)
        seeds = await extractor.extract_seeds_from_content(
            user_id=user_id,
            content=content,
            source_type=source_type,
            source_id=source_id,
        )

        return {"seeds": seeds, "count": len(seeds)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to extract seeds: {str(e)}"
        )


@router.post("/suggestions/generate")
async def generate_suggestions(
    user_id: str = Query(..., description="Profile ID"),
    days_back: int = Query(7, ge=1, le=30, description="Days to look back"),
):
    """Generate mindscape update suggestions from recent seeds"""
    try:
        from ...capabilities.semantic_seeds.services.suggestion_generator import (
            SuggestionGenerator,
        )
        from backend.app.services.agent_runner import AgentRunner

        agent_runner = AgentRunner()
        try:
            llm_provider = get_llm_provider_from_settings(agent_runner.llm_manager)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"LLM provider not configured: {e}"
            )

        generator = SuggestionGenerator(llm_provider=llm_provider)
        suggestions = await generator.generate_suggestions(
            user_id=user_id,
            days_back=days_back,
        )

        return {"suggestions": suggestions, "count": len(suggestions)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate suggestions: {str(e)}"
        )


@router.get("/suggestions")
async def list_suggestions(
    profile_id: str = Query(..., description="Profile ID"),
    status: Optional[str] = Query("pending", description="Filter by status"),
):
    """List suggestions for a profile"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        postgres_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        with psycopg2.connect(**postgres_config) as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT
                    id, user_id, suggestion_type, title, description,
                    suggested_data, source_seed_ids, source_summary,
                    confidence, status, generated_at
                FROM mindscape_suggestions
                WHERE user_id = %s AND status = %s
                ORDER BY generated_at DESC
                LIMIT 10
            """,
                (profile_id, status),
            )

            suggestions = [dict(row) for row in cursor.fetchall()]
            return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list suggestions: {str(e)}"
        )


@router.post("/suggestions/{suggestion_id}/review")
async def review_suggestion(
    suggestion_id: str = Path(..., description="Suggestion ID"),
    action: str = Query(..., description="Action: accept, dismiss, edit"),
    edited_data: Optional[Dict] = None,
):
    """Review a suggestion (accept, dismiss, or edit)"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        postgres_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        with psycopg2.connect(**postgres_config) as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                """
                SELECT * FROM mindscape_suggestions WHERE id = %s
            """,
                (suggestion_id,),
            )
            suggestion = cursor.fetchone()

            if not suggestion:
                raise HTTPException(status_code=404, detail="Suggestion not found")

            suggestion = dict(suggestion)

            cursor.execute(
                """
                UPDATE mindscape_suggestions
                SET status = %s, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = %s
            """,
                (action, suggestion_id),
            )

            if action == "accept":
                if (
                    suggestion["suggestion_type"] == "intent"
                    or suggestion["suggestion_type"] == "project"
                ):
                    intent = IntentCard(
                        id=str(uuid.uuid4()),
                        user_id=suggestion["user_id"],
                        title=edited_data.get("title", suggestion["title"])
                        if edited_data
                        else suggestion["title"],
                        description=edited_data.get(
                            "description", suggestion["description"]
                        )
                        if edited_data
                        else suggestion["description"],
                        status=IntentStatus.ACTIVE,
                        priority=PriorityLevel.MEDIUM,
                        tags=[],
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    store.create_intent(intent)
                    conn.commit()
                    return {"status": "accepted", "created_intent_id": intent.id}

            conn.commit()
            return {"status": action}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to review suggestion: {str(e)}"
        )


@router.get("/profiles/{user_id}/current-mode")
async def get_current_mode(user_id: str = Path(..., description="Profile ID")):
    """Get current mindscape mode (inferred from recent activity)"""
    try:
        intents = store.list_intents(user_id, status=IntentStatus.ACTIVE)
        intents = intents[:5] if len(intents) > 5 else intents

        import psycopg2
        from psycopg2.extras import RealDictCursor

        postgres_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        cutoff_date = datetime.utcnow() - timedelta(days=7)

        with psycopg2.connect(**postgres_config) as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT source_type, content, COUNT(*) as count
                FROM mindscape_personal
                WHERE user_id = %s AND updated_at >= %s
                GROUP BY source_type, content
                ORDER BY count DESC
                LIMIT 10
            """,
                (user_id, cutoff_date),
            )

            recent_seeds = [dict(row) for row in cursor.fetchall()]

        main_mode = "2025 創業者模式"
        weekly_focus = [intent.title for intent in intents[:3]]
        ai_assistants = ["平面設計助理", "內容編輯", "情緒陪練"]

        return {
            "main_mode": main_mode,
            "weekly_focus": weekly_focus,
            "ai_assistants": ai_assistants,
            "inferred_from": {
                "recent_intents": len(intents),
                "recent_seeds": len(recent_seeds),
                "time_range": "last_7_days",
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get current mode: {str(e)}"
        )
