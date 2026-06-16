"""
Mindscape API routes.

Handles profile and intent management endpoints.
"""

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Query

from backend.features.mindscape.route_state import governance_engine
from backend.features.mindscape.routes_core import playbook_completion_webhook_payload
from backend.features.mindscape.routes_intent_logs import router as intent_logs_router
from backend.features.mindscape.routes_onboarding import router as onboarding_router
from backend.features.mindscape.routes_profiles_intents import (
    router as profiles_intents_router,
)
from backend.features.mindscape.routes_suggestions import router as suggestions_router
from backend.features.mindscape.routes_timeline_entities import (
    router as timeline_entities_router,
)

router = APIRouter(tags=["mindscape"])
router.include_router(onboarding_router)


@router.post("/playbook/webhook")
async def playbook_completion_webhook(
    execution_id: str = Query(..., description="Execution ID"),
    playbook_code: str = Query(..., description="Playbook code"),
    user_id: str = Query("default-user", description="Profile ID"),
    output_data: Dict[str, Any] = Body(
        ..., description="Structured output from playbook"
    ),
):
    """
    Webhook endpoint for playbook completion.

    This is called automatically when a playbook execution completes.
    It handles:
    - Creating intent cards from project breakdown
    - Creating seeds from insights
    - Updating onboarding state
    """
    try:
        return await playbook_completion_webhook_payload(
            governance_engine=governance_engine,
            execution_id=execution_id,
            playbook_code=playbook_code,
            user_id=user_id,
            output_data=output_data,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to handle playbook webhook: {str(e)}"
        )


router.include_router(profiles_intents_router)
router.include_router(suggestions_router)
router.include_router(intent_logs_router)
router.include_router(timeline_entities_router)
