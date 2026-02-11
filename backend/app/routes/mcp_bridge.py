"""
MCP Bridge API Routes — Phase 1 (Strategy B)

Backend endpoints for MCP Gateway → Workspace communication.
These routes are registered in main.py via register_core_routes().

Endpoints:
  POST /api/v1/mcp/chat/sync          — Sync IDE conversation to WS timeline
  POST /api/v1/mcp/intent/submit      — Submit IDE-extracted intents
  POST /api/v1/mcp/intent/layout/execute — Execute IntentLayoutPlan
  POST /api/v1/mcp/project/detect     — Detect & create project from message

Design decisions (from gap_resolution.md):
  - profile_id fallback: "default-user"
  - conversation_id == thread_id (direct equivalence)
  - message_id must come from IDE; fallback to trace_id
  - ide_receipts skip WS-side LLM when present
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp-bridge"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
#  Request / Response Schemas
# ============================================================


class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = None


class IDEReceipt(BaseModel):
    """Governance Inv.3 — Receipts over Claims"""

    step: str = Field(
        ..., description="intent_extract | steward_analyze | project_detect"
    )
    trace_id: str
    output_hash: str = Field(..., description="SHA-256 of output")
    output_summary: Optional[Dict[str, Any]] = None
    completed_at: Optional[str] = None


class ChatSyncRequest(BaseModel):
    workspace_id: str
    conversation_id: str
    surface_type: str = Field(
        default="ide", description="cursor | windsurf | copilot | antigravity"
    )
    trace_id: Optional[str] = None
    profile_id: Optional[str] = None
    messages: List[ChatMessage]
    playbook_executed: Optional[str] = None
    ide_receipts: Optional[List[IDEReceipt]] = None


class ExtractedIntent(BaseModel):
    label: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="ide")
    metadata: Optional[Dict[str, Any]] = None


class IntentSubmitRequest(BaseModel):
    workspace_id: str
    message: str
    message_id: Optional[str] = None
    profile_id: Optional[str] = None
    extracted_intents: List[ExtractedIntent]
    extracted_themes: Optional[List[str]] = None


class IntentLayoutAction(BaseModel):
    """Maps to IntentOperation structure"""

    operation_type: str = Field(
        ..., description="CREATE_INTENT_CARD | UPDATE_INTENT_CARD | ARCHIVE"
    )
    intent_id: Optional[str] = None
    intent_data: Dict[str, Any] = Field(default_factory=dict)
    relation_signals: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    reasoning: str = ""


class LayoutPlan(BaseModel):
    long_term_intents: List[IntentLayoutAction] = Field(default_factory=list)
    ephemeral_tasks: Optional[List[Dict[str, Any]]] = None


class IntentLayoutExecuteRequest(BaseModel):
    workspace_id: str
    profile_id: Optional[str] = None
    layout_plan: LayoutPlan


class DetectedProject(BaseModel):
    mode: str = Field(
        default="project", description="quick_task | micro_flow | project"
    )
    project_type: Optional[str] = None
    project_title: Optional[str] = None
    playbook_sequence: Optional[List[str]] = None
    initial_spec_md: Optional[str] = None
    confidence: Optional[float] = None


class ProjectDetectRequest(BaseModel):
    workspace_id: str
    message: str
    profile_id: Optional[str] = None
    detected_project: DetectedProject


# ============================================================
#  POST /api/v1/mcp/chat/sync
# ============================================================


@router.post("/chat/sync")
async def chat_sync(req: ChatSyncRequest = Body(...)) -> Dict[str, Any]:
    """
    Sync IDE conversation to Workspace timeline.

    - Records each message as a timeline event
    - Skips WS-side LLM processing when ide_receipts cover the step
    - Returns list of hooks triggered and events emitted
    """
    profile_id = req.profile_id or "default-user"
    thread_id = req.conversation_id  # direct equivalence
    trace_id = req.trace_id or str(uuid.uuid4())

    try:
        from ..services.surface.event_stream import EventStreamService

        event_stream = EventStreamService()

        events_emitted = []
        hooks_triggered = []

        # Record each message as a timeline event
        for msg in req.messages:
            message_id = msg.message_id or trace_id
            event = event_stream.collect_event(
                workspace_id=req.workspace_id,
                source_surface=f"mcp_{req.surface_type}",
                event_type=f"chat_{msg.role}",
                payload={
                    "content": msg.content,
                    "role": msg.role,
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "trace_id": trace_id,
                    "timestamp": msg.timestamp or _utc_now().isoformat(),
                    "playbook_executed": req.playbook_executed,
                },
                actor_id=profile_id,
                correlation_id=trace_id,
            )
            events_emitted.append(
                event.event_id if hasattr(event, "event_id") else str(event)
            )

        # --------------------------------------------------------
        # Run event hooks (Phase 2a: idempotent hook runner)
        # --------------------------------------------------------
        try:
            from ..services.mcp_event_hooks import MCPEventHookService

            hook_service = MCPEventHookService(workspace_id=req.workspace_id)

            # Latest user message for hook processing
            user_messages = [m for m in req.messages if m.role == "user"]
            last_user_msg = user_messages[-1] if user_messages else None

            if last_user_msg:
                hook_results = await hook_service.on_chat_synced(
                    workspace_id=req.workspace_id,
                    profile_id=profile_id,
                    message=last_user_msg.content,
                    message_id=last_user_msg.message_id or trace_id,
                    trace_id=trace_id,
                    thread_id=thread_id,
                    ide_receipts=(
                        [r.model_dump() for r in req.ide_receipts]
                        if req.ide_receipts
                        else None
                    ),
                )
                hooks_triggered.extend(hook_results.triggered_hooks)
                events_emitted.extend(hook_results.events_emitted)

                # Log skipped hooks
                if hook_results.skipped_hooks:
                    logger.info(
                        f"chat_sync: Skipped hooks (IDE receipts): "
                        f"{hook_results.skipped_hooks} (trace={trace_id})"
                    )
        except ImportError:
            logger.debug("MCPEventHookService not available, skipping hooks")
        except Exception as hook_err:
            logger.warning(f"Event hook processing failed: {hook_err}")

        # Build receipt details for response (Phase 2b)
        receipt_details = []
        try:
            if hook_results:
                for d in hook_results.receipt_decisions:
                    receipt_details.append(
                        {
                            "step": d.step,
                            "action": "skipped" if not d.should_run else "ran",
                            "reason": d.reason,
                        }
                    )
        except NameError:
            pass  # hook_results not defined (ImportError path)

        return {
            "synced": True,
            "trace_id": trace_id,
            "thread_id": thread_id,
            "events_emitted": events_emitted,
            "hooks_triggered": hooks_triggered,
            "ide_receipts_applied": [
                d["step"] for d in receipt_details if d["action"] == "skipped"
            ],
            "receipt_details": receipt_details,
            "message_count": len(req.messages),
        }

    except Exception as e:
        logger.error(f"chat_sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat sync failed: {str(e)}")


# ============================================================
#  POST /api/v1/mcp/intent/submit
# ============================================================


@router.post("/intent/submit")
async def intent_submit(req: IntentSubmitRequest = Body(...)) -> Dict[str, Any]:
    """
    Submit IDE-extracted intents to Workspace.

    - Creates IntentTag entries with source=IDE
    - Skips WS-side IntentExtractor (IDE already did it)
    """
    profile_id = req.profile_id or "default-user"

    try:
        from ..models.mindscape import IntentTag, IntentSource, IntentTagStatus
        from ..services.stores.intent_tags_store import IntentTagsStore
        from ..services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        store.ensure_default_profile()
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        created_tags = []
        for intent in req.extracted_intents:
            tag = IntentTag(
                id=str(uuid.uuid4()),
                workspace_id=req.workspace_id,
                profile_id=profile_id,
                label=intent.label,
                confidence=intent.confidence,
                source=IntentSource.IDE,
                status=IntentTagStatus.CANDIDATE,
                message_id=req.message_id,
                metadata={
                    **(intent.metadata or {}),
                    "submitted_via": "mcp_bridge",
                    "original_message_preview": (
                        req.message[:200] if req.message else None
                    ),
                },
                created_at=_utc_now(),
            )
            try:
                intent_tags_store.create_intent_tag(tag)
                created_tags.append(
                    {
                        "id": tag.id,
                        "label": tag.label,
                        "confidence": tag.confidence,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to create IntentTag '{tag.label}': {e}")

        # Record themes if provided
        themes_recorded = 0
        if req.extracted_themes:
            # Store themes as IntentTags with lower confidence
            for theme in req.extracted_themes:
                try:
                    theme_tag = IntentTag(
                        id=str(uuid.uuid4()),
                        workspace_id=req.workspace_id,
                        profile_id=profile_id,
                        label=theme,
                        confidence=0.4,
                        source=IntentSource.IDE,
                        status=IntentTagStatus.CANDIDATE,
                        message_id=req.message_id,
                        metadata={"type": "theme", "submitted_via": "mcp_bridge"},
                        created_at=_utc_now(),
                    )
                    intent_tags_store.create_intent_tag(theme_tag)
                    themes_recorded += 1
                except Exception as e:
                    logger.warning(f"Failed to create theme tag '{theme}': {e}")

        return {
            "success": True,
            "intent_tags_created": len(created_tags),
            "themes_recorded": themes_recorded,
            "tags": created_tags,
        }

    except ImportError as e:
        logger.warning(f"Intent submit — missing dependency: {e}")
        raise HTTPException(status_code=501, detail="IntentTag stores not available")
    except Exception as e:
        logger.error(f"intent_submit failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Intent submission failed: {str(e)}"
        )


# ============================================================
#  POST /api/v1/mcp/intent/layout/execute
# ============================================================


@router.post("/intent/layout/execute")
async def intent_layout_execute(
    req: IntentLayoutExecuteRequest = Body(...),
) -> Dict[str, Any]:
    """
    Execute an IntentLayoutPlan — create/update IntentCards.

    This is a governed operation (requires confirmation in tool_access_policy).
    Uses IntentStewardService._execute_layout_plan internally.
    """
    profile_id = req.profile_id or "default-user"

    try:
        from ..models.mindscape import (
            IntentLayoutPlan,
            IntentOperation,
            EphemeralTask,
        )
        from ..services.mindscape_store import MindscapeStore
        from ..services.conversation.intent_steward import IntentStewardService

        store = MindscapeStore()
        store.ensure_default_profile()
        steward = IntentStewardService(store=store)

        # Build IntentLayoutPlan from request
        operations = []
        for action in req.layout_plan.long_term_intents:
            op = IntentOperation(
                operation_type=action.operation_type,
                intent_id=action.intent_id,
                intent_data=action.intent_data,
                relation_signals=action.relation_signals,
                confidence=action.confidence,
                reasoning=action.reasoning,
            )
            operations.append(op)

        ephemeral = []
        if req.layout_plan.ephemeral_tasks:
            for task_data in req.layout_plan.ephemeral_tasks:
                ephemeral.append(
                    EphemeralTask(
                        signal_id=task_data.get("signal_id", str(uuid.uuid4())),
                        title=task_data.get("title", ""),
                        description=task_data.get("description"),
                        reasoning=task_data.get("reasoning", ""),
                    )
                )

        layout_plan = IntentLayoutPlan(
            long_term_intents=operations,
            ephemeral_tasks=ephemeral,
            metadata={
                "source": "mcp_bridge",
                "workspace_id": req.workspace_id,
                "profile_id": profile_id,
                "timestamp": _utc_now().isoformat(),
            },
        )

        # Execute via steward (reuses existing logic)
        turn_id = f"mcp_{uuid.uuid4().hex[:8]}"
        await steward._execute_layout_plan(
            layout_plan=layout_plan,
            workspace_id=req.workspace_id,
            profile_id=profile_id,
            turn_id=turn_id,
        )

        executed_ops = layout_plan.metadata.get("executed_operations", [])

        return {
            "success": True,
            "executed": len(executed_ops),
            "operations": executed_ops,
            "turn_id": turn_id,
        }

    except ImportError as e:
        logger.warning(f"Layout execute — missing dependency: {e}")
        raise HTTPException(
            status_code=501, detail="IntentSteward service not available"
        )
    except Exception as e:
        logger.error(f"intent_layout_execute failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Layout execution failed: {str(e)}"
        )


# ============================================================
#  POST /api/v1/mcp/project/detect
# ============================================================


@router.post("/project/detect")
async def project_detect(req: ProjectDetectRequest = Body(...)) -> Dict[str, Any]:
    """
    Detect if a message suggests a new Project, dedup and create if so.

    This is a governed operation (requires confirmation in tool_access_policy).
    Uses ProjectSuggestion model for schema alignment.
    """
    profile_id = req.profile_id or "default-user"

    try:
        from ..models.project import ProjectSuggestion
        from ..services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        store.ensure_default_profile()

        # Build ProjectSuggestion from request (aligned with project.py fields)
        suggestion = ProjectSuggestion(
            mode=req.detected_project.mode,
            project_type=req.detected_project.project_type,
            project_title=req.detected_project.project_title,
            playbook_sequence=req.detected_project.playbook_sequence,
            initial_spec_md=req.detected_project.initial_spec_md,
            confidence=req.detected_project.confidence,
        )

        # Check for duplicate projects
        project_id = None
        created = False
        reason = None

        try:
            # Use existing project store to check duplicates
            existing_projects = (
                store.list_projects(profile_id=profile_id)
                if hasattr(store, "list_projects")
                else []
            )
            title_lower = (suggestion.project_title or "").lower().strip()

            duplicate = None
            for proj in existing_projects:
                if hasattr(proj, "title") and proj.title.lower().strip() == title_lower:
                    duplicate = proj
                    break

            if duplicate:
                project_id = duplicate.id if hasattr(duplicate, "id") else None
                reason = f"Duplicate project found: {duplicate.title if hasattr(duplicate, 'title') else 'unknown'}"
            else:
                # Create new project
                new_project_id = str(uuid.uuid4())
                try:
                    if hasattr(store, "create_project"):
                        result = store.create_project(
                            profile_id=profile_id,
                            title=suggestion.project_title or "Untitled Project",
                            description=suggestion.initial_spec_md or "",
                            project_type=suggestion.project_type,
                            metadata={
                                "mode": suggestion.mode,
                                "playbook_sequence": suggestion.playbook_sequence,
                                "confidence": suggestion.confidence,
                                "source": "mcp_bridge",
                                "workspace_id": req.workspace_id,
                            },
                        )
                        project_id = (
                            result.id if hasattr(result, "id") else new_project_id
                        )
                        created = True
                    else:
                        # Store doesn't support project creation yet
                        project_id = new_project_id
                        reason = (
                            "Project creation not yet supported — suggestion recorded"
                        )
                except Exception as e:
                    reason = f"Project creation failed: {str(e)}"

        except Exception as e:
            reason = f"Duplicate check failed: {str(e)}"

        return {
            "project_id": project_id,
            "created": created,
            "reason": reason,
            "suggestion": {
                "mode": suggestion.mode,
                "project_title": suggestion.project_title,
                "project_type": suggestion.project_type,
                "confidence": suggestion.confidence,
            },
        }

    except ImportError as e:
        logger.warning(f"Project detect — missing dependency: {e}")
        raise HTTPException(status_code=501, detail="Project models not available")
    except Exception as e:
        logger.error(f"project_detect failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Project detection failed: {str(e)}"
        )
