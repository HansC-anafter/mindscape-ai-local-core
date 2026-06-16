"""Mindscape onboarding route group."""

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from backend.features.mindscape.route_state import onboarding_service
from backend.features.mindscape.routes_core import (
    SelfIntroRequest,
    complete_self_intro_payload,
    complete_task2_payload,
    complete_task3_payload,
    get_onboarding_status_payload,
)

router = APIRouter()


@router.get("/onboarding/status")
async def get_onboarding_status(
    user_id: str = Query("default-user", description="Profile ID")
):
    """Get onboarding status for a profile"""
    try:
        return get_onboarding_status_payload(
            onboarding_service=onboarding_service,
            user_id=user_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get onboarding status: {str(e)}"
        )


@router.post("/onboarding/self-intro")
async def complete_self_intro(
    user_id: str = Query("default-user", description="Profile ID"),
    request: SelfIntroRequest = Body(...),
):
    """
    Complete task 1: Self introduction (starter role card)

    User provides:
    - identity: What they're currently doing
    - solving: What they want to accomplish
    - thinking: What's on their mind / challenges
    """
    try:
        return complete_self_intro_payload(
            onboarding_service=onboarding_service,
            user_id=user_id,
            identity=request.identity,
            solving=request.solving,
            thinking=request.thinking,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to complete self intro: {str(e)}"
        )


@router.post("/onboarding/complete-task2")
async def complete_task2(
    user_id: str = Query("default-user", description="Profile ID"),
    execution_id: Optional[str] = Query(None, description="Playbook execution ID"),
    intent_id: Optional[str] = Query(None, description="Created intent card ID"),
):
    """
    Complete task 2: First long-term project breakdown

    Called after user completes the project breakdown playbook
    """
    try:
        return complete_task2_payload(
            onboarding_service=onboarding_service,
            user_id=user_id,
            execution_id=execution_id,
            intent_id=intent_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to complete task 2: {str(e)}"
        )


@router.post("/onboarding/complete-task3")
async def complete_task3(
    user_id: str = Query("default-user", description="Profile ID"),
    execution_id: Optional[str] = Query(None, description="Playbook execution ID"),
    created_seeds_count: int = Query(0, description="Number of seeds created"),
):
    """
    Complete task: Weekly work rhythm review

    Called after user completes the weekly review playbook
    """
    try:
        return complete_task3_payload(
            onboarding_service=onboarding_service,
            user_id=user_id,
            execution_id=execution_id,
            created_seeds_count=created_seeds_count,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to complete task 3: {str(e)}"
        )
