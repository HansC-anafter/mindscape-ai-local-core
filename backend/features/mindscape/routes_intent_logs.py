"""Mindscape intent-log route group."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from backend.app.models.mindscape import IntentLog
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
from backend.features.mindscape.route_state import logger, store
from backend.features.mindscape.routes_core import (
    AnnotateIntentLogRequest,
    ReplayIntentLogRequest,
    annotate_intent_log_record,
    get_intent_log_payload,
    list_intent_logs_payload,
)

router = APIRouter()


@router.get("/intent-logs", response_model=List[IntentLog])
async def list_intent_logs(
    profile_id: Optional[str] = Query(None, description="Filter by profile ID"),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    has_override: Optional[bool] = Query(
        None, description="Filter logs with user override"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs"),
):
    """List intent logs with optional filters"""
    try:
        return list_intent_logs_payload(
            store=store,
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            has_override=has_override,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list intent logs: {str(e)}"
        )


@router.get("/intent-logs/{log_id}", response_model=IntentLog)
async def get_intent_log(log_id: str = Path(..., description="Intent log ID")):
    """Get a specific intent log by ID"""
    try:
        return get_intent_log_payload(store=store, log_id=log_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get intent log: {str(e)}"
        )


@router.post("/intent-logs/{log_id}/annotate", response_model=IntentLog)
async def annotate_intent_log(
    log_id: str = Path(..., description="Intent log ID"),
    request: AnnotateIntentLogRequest = Body(...),
):
    """Annotate an intent log with correct answer"""
    try:
        return annotate_intent_log_record(
            store=store,
            log_id=log_id,
            request=request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to annotate intent log: {str(e)}"
        )


@router.post("/intent-logs/replay")
async def replay_intent_logs(
    log_ids: List[str] = Body(..., description="List of intent log IDs to replay"),
    request: ReplayIntentLogRequest = Body(...),
):
    """Replay intent logs with new settings"""
    try:
        from backend.app.services.agent_runner import LLMProviderManager
        from backend.app.services.intent_analyzer import IntentPipeline

        llm_provider = None
        if request.model:
            from backend.app.shared.llm_provider_helper import (
                create_llm_provider_manager,
            )

            llm_manager = create_llm_provider_manager()
            try:
                llm_provider = get_llm_provider_from_settings(llm_manager)
            except ValueError as e:
                logger.warning(
                    f"LLM provider not available: {e}, continuing without LLM"
                )
                llm_provider = None

        pipeline = IntentPipeline(
            llm_provider=llm_provider,
            use_llm=request.use_llm if request.use_llm is not None else True,
            rule_priority=request.rule_priority
            if request.rule_priority is not None
            else True,
            enable_logging=False,
        )

        results = []
        for log_id in log_ids:
            try:
                result = await pipeline.replay_intent_log(
                    log_id=log_id,
                    llm_provider=llm_provider,
                    use_llm=request.use_llm if request.use_llm is not None else True,
                    rule_priority=request.rule_priority
                    if request.rule_priority is not None
                    else True,
                )
                results.append(
                    {
                        "log_id": log_id,
                        "success": True,
                        "result": {
                            "interaction_type": result.interaction_type.value
                            if result.interaction_type
                            else None,
                            "task_domain": result.task_domain.value
                            if result.task_domain
                            else None,
                            "playbook_code": result.selected_playbook_code,
                        },
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "log_id": log_id,
                        "success": False,
                        "error": str(e),
                    }
                )

        return {
            "total": len(log_ids),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to replay intent logs: {str(e)}"
        )


@router.get("/intent-logs/evaluate")
async def evaluate_intent_logs(
    profile_id: Optional[str] = Query(None, description="Filter by profile ID"),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
):
    """Evaluate intent logs and calculate metrics"""
    try:
        from backend.app.services.intent_analyzer import IntentPipeline

        pipeline = IntentPipeline(enable_logging=False)

        start = datetime.fromisoformat(start_time) if start_time else None
        end = datetime.fromisoformat(end_time) if end_time else None

        metrics = pipeline.evaluate_intent_logs(
            profile_id=profile_id,
            start_time=start,
            end_time=end,
        )

        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to evaluate intent logs: {str(e)}"
        )
