"""
Mindscape API routes
Handles profile and intent management endpoints
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Path, Query, Body

from backend.app.models.mindscape import (
    CreateIntentRequest,
    CreateProfileRequest,
    Entity,
    EventActor,
    EventType,
    IntentCard,
    IntentLog,
    IntentStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    Tag,
    UpdateIntentRequest,
    UpdateProfileRequest,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.mindscape_onboarding import MindscapeOnboardingService
from backend.app.services.orchestration.governance_engine import GovernanceEngine
from backend.app.services.intent_analyzer import IntentPipeline
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
from backend.features.mindscape.routes_core import (
    AnnotateIntentLogRequest,
    ReplayIntentLogRequest,
    SelfIntroRequest,
    archive_intent,
    annotate_intent_log_record,
    associate_intent_playbook_payload,
    complete_self_intro_payload,
    complete_task2_payload,
    complete_task3_payload,
    create_profile_record,
    create_entity_record,
    create_tag_record,
    get_entities_by_tag_payload,
    get_entity_payload,
    get_intent_playbooks_payload,
    get_intent_log_payload,
    get_intent_or_404,
    get_onboarding_status_payload,
    get_project_timeline_payload,
    get_profile_or_404,
    get_timeline_payload,
    list_intent_logs_payload,
    list_intents_payload,
    list_entities_payload,
    list_tags_payload,
    playbook_completion_webhook_payload,
    remove_intent_playbook_payload,
    tag_entity_record,
    untag_entity_record,
    update_entity_record,
    update_profile_record,
)

router = APIRouter(tags=["mindscape"])
logger = logging.getLogger(__name__)

# Initialize store, onboarding service, and completion ingress façade
store = MindscapeStore()
onboarding_service = MindscapeOnboardingService(store)
governance_engine = GovernanceEngine()


# ============================================================================
# Onboarding Endpoints
# ============================================================================

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
        raise HTTPException(status_code=500, detail=f"Failed to get onboarding status: {str(e)}")


@router.post("/onboarding/self-intro")
async def complete_self_intro(
    user_id: str = Query("default-user", description="Profile ID"),
    request: SelfIntroRequest = Body(...)
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
        raise HTTPException(status_code=500, detail=f"Failed to complete self intro: {str(e)}")


@router.post("/onboarding/complete-task2")
async def complete_task2(
    user_id: str = Query("default-user", description="Profile ID"),
    execution_id: Optional[str] = Query(None, description="Playbook execution ID"),
    intent_id: Optional[str] = Query(None, description="Created intent card ID")
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
        raise HTTPException(status_code=500, detail=f"Failed to complete task 2: {str(e)}")


@router.post("/onboarding/complete-task3")
async def complete_task3(
    user_id: str = Query("default-user", description="Profile ID"),
    execution_id: Optional[str] = Query(None, description="Playbook execution ID"),
    created_seeds_count: int = Query(0, description="Number of seeds created")
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
        raise HTTPException(status_code=500, detail=f"Failed to complete task 3: {str(e)}")


@router.post("/playbook/webhook")
async def playbook_completion_webhook(
    execution_id: str = Query(..., description="Execution ID"),
    playbook_code: str = Query(..., description="Playbook code"),
    user_id: str = Query("default-user", description="Profile ID"),
    output_data: Dict[str, Any] = Body(..., description="Structured output from playbook")
):
    """
    Webhook endpoint for playbook completion

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
        raise HTTPException(status_code=500, detail=f"Failed to handle playbook webhook: {str(e)}")


# ============================================================================
# Profile endpoints
# ============================================================================

@router.post("/profiles", response_model=MindscapeProfile, status_code=201)
async def create_profile(request: CreateProfileRequest):
    """Create a new mindscape profile"""
    try:
        return create_profile_record(store=store, request=request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}")


@router.get("/profiles/{user_id}", response_model=MindscapeProfile)
async def get_profile(user_id: str = Path(..., description="Profile ID")):
    """Get profile by ID"""
    return get_profile_or_404(store=store, user_id=user_id)


@router.put("/profiles/{user_id}", response_model=MindscapeProfile)
async def update_profile(
    user_id: str = Path(..., description="Profile ID"),
    request: UpdateProfileRequest = None
):
    """Update an existing profile"""
    try:
        return update_profile_record(
            store=store,
            user_id=user_id,
            request=request,
            logger=logger,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")


# Intent endpoints

@router.post("/profiles/{user_id}/intents", response_model=IntentCard, status_code=201)
async def create_intent(
    user_id: str = Path(..., description="Profile ID"),
    request: CreateIntentRequest = None
):
    """Create a new intent card"""
    if not request:
        raise HTTPException(status_code=400, detail="Create request required")

    # Verify profile exists
    profile = store.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    try:
        intent = IntentCard(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=request.title,
            description=request.description,
            priority=request.priority,
            tags=request.tags,
            category=request.category,
            due_date=request.due_date,
            parent_intent_id=request.parent_intent_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        created = store.create_intent(intent)

        # Record intent creation event
        try:
            is_high_priority = created.priority in ["high", "critical"]
            intent_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.USER,
                channel="api",
                profile_id=user_id,
                project_id=None,
                workspace_id=None,
                event_type=EventType.INTENT_CREATED,
                payload={
                    "intent_id": created.id,
                    "title": created.title,
                    "description": created.description,
                    "status": created.status.value,
                    "priority": created.priority.value
                },
                entity_ids=[created.id],
                metadata={
                    "should_embed": is_high_priority,
                    "is_artifact": is_high_priority
                }
            )
            # Only generate embedding for high-priority intents
            store.create_event(intent_event, generate_embedding=is_high_priority)
        except Exception as e:
            logger.warning(f"Failed to record intent creation event: {e}")

        return created

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create intent: {str(e)}")


@router.get("/profiles/{user_id}/intents", response_model=List[IntentCard])
async def list_intents(
    user_id: str = Path(..., description="Profile ID"),
    status: Optional[IntentStatus] = Query(None, description="Filter by status"),
    priority: Optional[PriorityLevel] = Query(None, description="Filter by priority")
):
    """List intents for a profile"""
    return list_intents_payload(
        store=store,
        user_id=user_id,
        status=status,
        priority=priority,
    )


@router.get("/intents/{intent_id}", response_model=IntentCard)
async def get_intent(intent_id: str = Path(..., description="Intent ID")):
    """Get intent by ID"""
    return get_intent_or_404(store=store, intent_id=intent_id)


@router.put("/intents/{intent_id}", response_model=IntentCard)
async def update_intent(
    intent_id: str = Path(..., description="Intent ID"),
    request: UpdateIntentRequest = None
):
    """Update an existing intent"""
    if not request:
        raise HTTPException(status_code=400, detail="Update request required")

    intent = store.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    # Apply updates
    if request.title is not None:
        intent.title = request.title
    if request.description is not None:
        intent.description = request.description
    if request.status is not None:
        intent.status = request.status
    if request.priority is not None:
        intent.priority = request.priority
    if request.tags is not None:
        intent.tags = request.tags
    if request.category is not None:
        intent.category = request.category
    if request.progress_percentage is not None:
        intent.progress_percentage = request.progress_percentage
    if request.due_date is not None:
        intent.due_date = request.due_date
    if request.metadata is not None:
        intent.metadata = request.metadata

    # Update timestamps
    if request.status == IntentStatus.COMPLETED and not intent.completed_at:
        intent.completed_at = datetime.utcnow()
    if request.status == IntentStatus.ACTIVE and not intent.started_at:
        intent.started_at = datetime.utcnow()

    intent.updated_at = datetime.utcnow()
    is_completed = intent.status == IntentStatus.COMPLETED

    # Save updated intent (simplified - in production, use store.update_intent)
    # For now, we'll delete and recreate (not ideal, but works for MVP)
    # TODO: Implement proper update method in store
    store.create_intent(intent)  # This will overwrite due to same ID

    # Record intent update event
    try:
        update_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="api",
            profile_id=intent.user_id,
            project_id=None,
            workspace_id=None,
            event_type=EventType.INTENT_UPDATED,
            payload={
                "intent_id": intent.id,
                "title": intent.title,
                "description": intent.description,
                "status": intent.status.value,
                "priority": intent.priority.value,
                "updated_fields": [k for k in request.dict(exclude_unset=True).keys() if k in ['title', 'description', 'status', 'priority', 'tags', 'category']]
            },
            entity_ids=[intent.id],
            metadata={
                "should_embed": is_completed or intent.priority in ["high", "critical"],
                "is_artifact": is_completed
            }
        )
        # Generate embedding only if completed or high priority
        store.create_event(update_event, generate_embedding=is_completed or intent.priority in ["high", "critical"])
    except Exception as e:
        logger.warning(f"Failed to record intent update event: {e}")

    return intent


@router.delete("/intents/{intent_id}", status_code=204)
async def delete_intent(intent_id: str = Path(..., description="Intent ID")):
    """Delete an intent"""
    archive_intent(store=store, intent_id=intent_id)
    return None


@router.get("/intents/{intent_id}/playbooks", response_model=List[str])
async def get_intent_playbooks(intent_id: str = Path(..., description="Intent ID")):
    """Get playbook codes associated with an intent"""
    return get_intent_playbooks_payload(store=store, intent_id=intent_id)


@router.post("/intents/{intent_id}/playbooks/{playbook_code}", status_code=201)
async def associate_intent_playbook(
    intent_id: str = Path(..., description="Intent ID"),
    playbook_code: str = Path(..., description="Playbook code")
):
    """Associate a playbook with an intent"""
    return await associate_intent_playbook_payload(
        store=store,
        intent_id=intent_id,
        playbook_code=playbook_code,
    )


@router.delete("/intents/{intent_id}/playbooks/{playbook_code}", status_code=204)
async def remove_intent_playbook(
    intent_id: str = Path(..., description="Intent ID"),
    playbook_code: str = Path(..., description="Playbook code")
):
    """Remove association between intent and playbook"""
    remove_intent_playbook_payload(
        store=store,
        intent_id=intent_id,
        playbook_code=playbook_code,
    )
    return None


# Seed extraction endpoints

@router.post("/seeds/extract")
async def extract_seeds(
    user_id: str = Query(..., description="Profile ID"),
    source_type: str = Query(..., description="Source type: execution, conversation, tool_call"),
    source_id: Optional[str] = Query(None, description="Source ID"),
    content: str = Query(..., description="Content to extract seeds from")
):
    """Extract seeds from content (called automatically after executions)"""
    try:
        from ...capabilities.semantic_seeds.services.seed_extractor import SeedExtractor
        from backend.app.services.agent_runner import AgentRunner

        # Get LLM provider
        agent_runner = AgentRunner()
        try:
            llm_provider = get_llm_provider_from_settings(agent_runner.llm_manager)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"LLM provider not configured: {e}")

        extractor = SeedExtractor(llm_provider=llm_provider)
        seeds = await extractor.extract_seeds_from_content(
            user_id=user_id,
            content=content,
            source_type=source_type,
            source_id=source_id
        )

        return {"seeds": seeds, "count": len(seeds)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract seeds: {str(e)}")


# Suggestion generation endpoints

@router.post("/suggestions/generate")
async def generate_suggestions(
    user_id: str = Query(..., description="Profile ID"),
    days_back: int = Query(7, ge=1, le=30, description="Days to look back")
):
    """Generate mindscape update suggestions from recent seeds"""
    try:
        from ...capabilities.semantic_seeds.services.suggestion_generator import SuggestionGenerator
        from backend.app.services.agent_runner import AgentRunner

        # Get LLM provider
        agent_runner = AgentRunner()
        try:
            llm_provider = get_llm_provider_from_settings(agent_runner.llm_manager)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"LLM provider not configured: {e}")

        generator = SuggestionGenerator(llm_provider=llm_provider)
        suggestions = await generator.generate_suggestions(
            user_id=user_id,
            days_back=days_back
        )

        return {"suggestions": suggestions, "count": len(suggestions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {str(e)}")


@router.get("/suggestions")
async def list_suggestions(
    profile_id: str = Query(..., description="Profile ID"),
    status: Optional[str] = Query("pending", description="Filter by status")
):
    """List suggestions for a profile"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        import os

        postgres_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        with psycopg2.connect(**postgres_config) as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT
                    id, user_id, suggestion_type, title, description,
                    suggested_data, source_seed_ids, source_summary,
                    confidence, status, generated_at
                FROM mindscape_suggestions
                WHERE user_id = %s AND status = %s
                ORDER BY generated_at DESC
                LIMIT 10
            ''', (profile_id, status))

            suggestions = [dict(row) for row in cursor.fetchall()]
            return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list suggestions: {str(e)}")


@router.post("/suggestions/{suggestion_id}/review")
async def review_suggestion(
    suggestion_id: str = Path(..., description="Suggestion ID"),
    action: str = Query(..., description="Action: accept, dismiss, edit"),
    edited_data: Optional[Dict] = None
):
    """Review a suggestion (accept, dismiss, or edit)"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        import os
        import json

        postgres_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        with psycopg2.connect(**postgres_config) as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get suggestion
            cursor.execute('''
                SELECT * FROM mindscape_suggestions WHERE id = %s
            ''', (suggestion_id,))
            suggestion = cursor.fetchone()

            if not suggestion:
                raise HTTPException(status_code=404, detail="Suggestion not found")

            suggestion = dict(suggestion)

            # Update status
            cursor.execute('''
                UPDATE mindscape_suggestions
                SET status = %s, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = %s
            ''', (action, suggestion_id))

            # If accepted, create intent or update profile
            if action == "accept":
                if suggestion['suggestion_type'] == 'intent' or suggestion['suggestion_type'] == 'project':
                    # Create intent card
                    intent = IntentCard(
                        id=str(uuid.uuid4()),
                        user_id=suggestion['user_id'],
                        title=edited_data.get('title', suggestion['title']) if edited_data else suggestion['title'],
                        description=edited_data.get('description', suggestion['description']) if edited_data else suggestion['description'],
                        status=IntentStatus.ACTIVE,
                        priority=PriorityLevel.MEDIUM,
                        tags=[],
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    store.create_intent(intent)
                    conn.commit()
                    return {"status": "accepted", "created_intent_id": intent.id}

            conn.commit()
            return {"status": action}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to review suggestion: {str(e)}")


@router.get("/profiles/{user_id}/current-mode")
async def get_current_mode(user_id: str = Path(..., description="Profile ID")):
    """Get current mindscape mode (inferred from recent activity)"""
    try:
        # Get recent intents
        intents = store.list_intents(user_id, status=IntentStatus.ACTIVE)
        # Limit to 5 most recent
        intents = intents[:5] if len(intents) > 5 else intents

        # Get recent seeds (last 7 days)
        import psycopg2
        from psycopg2.extras import RealDictCursor
        import os
        from datetime import datetime, timedelta

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
            cursor.execute('''
                SELECT source_type, content, COUNT(*) as count
                FROM mindscape_personal
                WHERE user_id = %s AND updated_at >= %s
                GROUP BY source_type, content
                ORDER BY count DESC
                LIMIT 10
            ''', (user_id, cutoff_date))

            recent_seeds = [dict(row) for row in cursor.fetchall()]

        # Infer mode (simplified version)
        main_mode = "2025 創業者模式"  # TODO: Use LLM to infer from intents/seeds
        weekly_focus = [intent.title for intent in intents[:3]]
        ai_assistants = ["平面設計助理", "內容編輯", "情緒陪練"]  # TODO: Infer from recent executions

        return {
            "main_mode": main_mode,
            "weekly_focus": weekly_focus,
            "ai_assistants": ai_assistants,
            "inferred_from": {
                "recent_intents": len(intents),
                "recent_seeds": len(recent_seeds),
                "time_range": "last_7_days"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current mode: {str(e)}")


# ============================================================================
# Intent Log Endpoints (for offline optimization)
# ============================================================================

@router.get("/intent-logs", response_model=List[IntentLog])
async def list_intent_logs(
    profile_id: Optional[str] = Query(None, description="Filter by profile ID"),
    start_time: Optional[str] = Query(None, description="Start time filter (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    has_override: Optional[bool] = Query(None, description="Filter logs with user override"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs")
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
        raise HTTPException(status_code=500, detail=f"Failed to list intent logs: {str(e)}")


@router.get("/intent-logs/{log_id}", response_model=IntentLog)
async def get_intent_log(
    log_id: str = Path(..., description="Intent log ID")
):
    """Get a specific intent log by ID"""
    try:
        return get_intent_log_payload(store=store, log_id=log_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get intent log: {str(e)}")


@router.post("/intent-logs/{log_id}/annotate", response_model=IntentLog)
async def annotate_intent_log(
    log_id: str = Path(..., description="Intent log ID"),
    request: AnnotateIntentLogRequest = Body(...)
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
        raise HTTPException(status_code=500, detail=f"Failed to annotate intent log: {str(e)}")


@router.post("/intent-logs/replay")
async def replay_intent_logs(
    log_ids: List[str] = Body(..., description="List of intent log IDs to replay"),
    request: ReplayIntentLogRequest = Body(...)
):
    """Replay intent logs with new settings"""
    try:
        from backend.app.services.agent_runner import LLMProviderManager

        # Initialize pipeline
        llm_provider = None
        if request.model:
            from backend.app.shared.llm_provider_helper import create_llm_provider_manager
            llm_manager = create_llm_provider_manager()
            try:
                llm_provider = get_llm_provider_from_settings(llm_manager)
            except ValueError as e:
                logger.warning(f"LLM provider not available: {e}, continuing without LLM")
                llm_provider = None

        pipeline = IntentPipeline(
            llm_provider=llm_provider,
            use_llm=request.use_llm if request.use_llm is not None else True,
            rule_priority=request.rule_priority if request.rule_priority is not None else True,
            enable_logging=False
        )

        results = []
        for log_id in log_ids:
            try:
                result = await pipeline.replay_intent_log(
                    log_id=log_id,
                    llm_provider=llm_provider,
                    use_llm=request.use_llm if request.use_llm is not None else True,
                    rule_priority=request.rule_priority if request.rule_priority is not None else True
                )
                results.append({
                    "log_id": log_id,
                    "success": True,
                    "result": {
                        "interaction_type": result.interaction_type.value if result.interaction_type else None,
                        "task_domain": result.task_domain.value if result.task_domain else None,
                        "playbook_code": result.selected_playbook_code
                    }
                })
            except Exception as e:
                results.append({
                    "log_id": log_id,
                    "success": False,
                    "error": str(e)
                })

        return {
            "total": len(log_ids),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to replay intent logs: {str(e)}")


@router.get("/intent-logs/evaluate")
async def evaluate_intent_logs(
    profile_id: Optional[str] = Query(None, description="Filter by profile ID"),
    start_time: Optional[str] = Query(None, description="Start time filter (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)")
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
            end_time=end
        )

        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate intent logs: {str(e)}")


# ============================================================================
# Mindspace Viewer Endpoints (A.3)
# ============================================================================

@router.get("/timeline")
async def get_timeline(
    profile_id: str = Query(..., description="Profile ID"),
    start_time: Optional[str] = Query(None, description="Start time filter (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events")
):
    """Get mindspace timeline events"""
    try:
        return get_timeline_payload(
            store=store,
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get timeline: {str(e)}")


@router.get("/entities", response_model=List[Entity])
async def list_entities(
    profile_id: str = Query(..., description="Profile ID"),
    entity_type: Optional[str] = Query(None, description="Entity type filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of entities")
):
    """Get entities list"""
    try:
        return list_entities_payload(
            store=store,
            profile_id=profile_id,
            entity_type=entity_type,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list entities: {str(e)}")


@router.get("/projects/{project_id}/timeline")
async def get_project_timeline(
    project_id: str = Path(..., description="Project ID"),
    profile_id: Optional[str] = Query(None, description="Profile ID (optional, for validation)"),
    start_time: Optional[str] = Query(None, description="Start time filter (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events")
):
    """Get timeline for a specific project"""
    try:
        return get_project_timeline_payload(
            store=store,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get project timeline: {str(e)}")


@router.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(
    entity_id: str = Path(..., description="Entity ID")
):
    """Get a specific entity by ID"""
    try:
        return get_entity_payload(store=store, entity_id=entity_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get entity: {str(e)}")


@router.post("/entities", response_model=Entity, status_code=201)
async def create_entity(
    entity: Entity = Body(...)
):
    """Create a new entity"""
    try:
        return create_entity_record(store=store, entity=entity)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create entity: {str(e)}")


@router.put("/entities/{entity_id}", response_model=Entity)
async def update_entity(
    entity_id: str = Path(..., description="Entity ID"),
    updates: Dict[str, Any] = Body(...)
):
    """Update an entity"""
    try:
        return update_entity_record(store=store, entity_id=entity_id, updates=updates)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update entity: {str(e)}")


@router.get("/tags", response_model=List[Tag])
async def list_tags(
    profile_id: str = Query(..., description="Profile ID"),
    category: Optional[str] = Query(None, description="Tag category filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tags")
):
    """Get tags list"""
    try:
        return list_tags_payload(
            store=store,
            profile_id=profile_id,
            category=category,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tags: {str(e)}")


@router.post("/tags", response_model=Tag, status_code=201)
async def create_tag(
    tag: Tag = Body(...)
):
    """Create a new tag"""
    try:
        return create_tag_record(store=store, tag=tag)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tag: {str(e)}")


@router.post("/entities/{entity_id}/tags/{tag_id}")
async def tag_entity(
    entity_id: str = Path(..., description="Entity ID"),
    tag_id: str = Path(..., description="Tag ID"),
    value: Optional[str] = Body(None, description="Optional tag value")
):
    """Tag an entity with a tag"""
    try:
        return tag_entity_record(
            store=store,
            entity_id=entity_id,
            tag_id=tag_id,
            value=value,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to tag entity: {str(e)}")


@router.delete("/entities/{entity_id}/tags/{tag_id}", status_code=204)
async def untag_entity(
    entity_id: str = Path(..., description="Entity ID"),
    tag_id: str = Path(..., description="Tag ID")
):
    """Remove a tag from an entity"""
    try:
        untag_entity_record(store=store, entity_id=entity_id, tag_id=tag_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to untag entity: {str(e)}")


@router.get("/tags/{tag_id}/entities", response_model=List[Entity])
async def get_entities_by_tag(
    tag_id: str = Path(..., description="Tag ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of entities")
):
    """Get all entities tagged with a specific tag"""
    try:
        return get_entities_by_tag_payload(store=store, tag_id=tag_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get entities by tag: {str(e)}")
