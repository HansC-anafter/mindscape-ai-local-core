"""
Decision Cards API Routes

Provides APIs for managing decision cards (from unified decision system).
Decision cards are projected from DECISION_REQUIRED events to the right panel.
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from fastapi import APIRouter, HTTPException, Path, Body, Query
from pydantic import BaseModel, Field

from backend.app.models.mindscape import IntentLog
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.decision.coordinator import UnifiedDecisionCoordinator
from backend.app.services.decision.coordinator_factory import (
    create_decision_coordinator,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["decision-cards"])
logger = logging.getLogger(__name__)


class ConfirmDecisionRequest(BaseModel):
    """Request model for confirming a decision"""

    action: str = Field(
        ..., description="Action: confirm | reject | clarify | override"
    )
    clarificationAnswers: Optional[Dict[str, str]] = Field(
        None, description="Answers to clarification questions"
    )
    providedInputs: Optional[Dict[str, Any]] = Field(
        None, description="Provided inputs for missing inputs"
    )
    overridePlaybookCode: Optional[str] = Field(
        None, description="Override playbook code"
    )
    overrideReason: Optional[str] = Field(None, description="Reason for override")
    comment: Optional[str] = Field(None, description="Optional comment")


@router.get("/{workspace_id}/decision-cards")
async def list_decision_cards(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    status: Optional[str] = Query(
        None, description="Filter by status: OPEN | NEED_INFO | READY | DONE | REJECTED"
    ),
    decision_method: Optional[str] = Query(
        "unified_decision_coordinator", description="Filter by decision method"
    ),
    include_legacy: bool = Query(False, description="Include legacy PendingTasks"),
):
    """
    List decision cards for a workspace

    Returns decision cards from IntentLog (unified_decision_coordinator) and optionally legacy tasks.
    """
    try:
        store = MindscapeStore()

        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        # Query IntentLogs with unified_decision_coordinator
        # Use workspace_id filter directly for better performance
        filtered_logs = await asyncio.to_thread(
            store.intent_logs.list_intent_logs,
            profile_id=None,
            workspace_id=workspace_id,
            project_id=project_id,
            start_time=None,
            end_time=None,
            has_override=None,
            limit=1000,
        )

        # Filter by decision_method
        filtered_logs = [
            log
            for log in filtered_logs
            and log.metadata.get("decision_method") == decision_method
        ]

        # If no logs found with None profile_id, try querying with empty string
        if not filtered_logs:
            try:
                all_logs = await asyncio.to_thread(
                    store.intent_logs.list_intent_logs,
                    profile_id="",
                    start_time=None,
                    end_time=None,
                    has_override=None,
                    limit=1000,
                )
                filtered_logs = [
                    log
                    for log in all_logs
                    if log.workspace_id == workspace_id
                    and log.metadata.get("decision_method") == decision_method
                ]
            except Exception:
                pass

        # Filter by project_id if provided
        if project_id:
            filtered_logs = [
                log for log in filtered_logs if log.project_id == project_id
            ]

        # Convert to decision cards
        cards = []
        for log in filtered_logs:
            final_decision = log.final_decision or {}

            # Check if requires user approval
            requires_approval = final_decision.get("requires_user_approval", False)
            can_auto_execute = final_decision.get("can_auto_execute", False)

            # Determine status
            playbook_contribution = final_decision.get("playbook_contribution", {})
            clarification_questions = playbook_contribution.get(
                "clarification_questions", []
            )
            missing_inputs = final_decision.get("intent_contribution", {}).get(
                "missing_inputs", []
            ) + playbook_contribution.get("missing_inputs", [])

            card_status = "OPEN"
            if clarification_questions or missing_inputs:
                card_status = "NEED_INFO"
            elif can_auto_execute:
                card_status = "READY"

            # Filter by status if provided
            if status and card_status != status:
                continue

            # Extract assignment info from user_override
            assignee = None
            watchers = []
            if log.user_override and isinstance(log.user_override, dict):
                assignment = log.user_override.get("assignment", {})
                if isinstance(assignment, dict):
                    assignee = assignment.get("assignee")
                    watchers = assignment.get("watchers", [])
                    if not isinstance(watchers, list):
                        watchers = []

            cards.append(
                {
                    "id": log.id,
                    "decisionId": final_decision.get("decision_id", log.id),
                    "intentLogId": log.id,
                    "timestamp": (
                        log.timestamp.isoformat()
                        if isinstance(log.timestamp, datetime)
                        else log.timestamp
                    ),
                    "workspaceId": log.workspace_id,
                    "projectId": log.project_id,
                    "profileId": log.profile_id,
                    "rawInput": log.raw_input,
                    "selectedPlaybookCode": final_decision.get(
                        "selected_playbook_code"
                    ),
                    "canAutoExecute": can_auto_execute,
                    "requiresUserApproval": requires_approval,
                    "status": card_status,
                    "priority": "blocker" if requires_approval else "normal",
                    "intentContribution": final_decision.get("intent_contribution", {}),
                    "playbookContribution": playbook_contribution,
                    "conflicts": final_decision.get("conflicts", []),
                    "assignee": assignee,
                    "watchers": watchers,
                }
            )

        # Get legacy tasks if requested
        legacy_tasks = []
        if include_legacy:
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore(db_path=store.db_path)
            # TODO: Query legacy tasks and mark as legacy
            pass

        # Calculate assignedToMe count
        # Note: This requires current_user_id to be passed or extracted from auth
        # For now, we'll return 0 and let frontend calculate based on workspace.owner_user_id
        # Frontend can filter cards by assignee/watchers using the assignment data in each card
        assigned_to_me_count = 0

        return {
            "cards": cards,
            "total": len(cards),
            "blockers": len(
                [
                    c
                    for c in cards
                    if c["priority"] == "blocker" and c["status"] == "OPEN"
                ]
            ),
            "assignedToMe": assigned_to_me_count,  # Frontend will calculate based on workspace.owner_user_id
            "legacyTasks": legacy_tasks,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list decision cards: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list decision cards: {str(e)}"
        )


@router.post("/{workspace_id}/decision-cards/{card_id}/confirm")
async def confirm_decision(
    workspace_id: str = Path(..., description="Workspace ID"),
    card_id: str = Path(..., description="Decision card ID (IntentLog.id)"),
    request: ConfirmDecisionRequest = Body(...),
):
    """
    Confirm a decision card

    Actions:
    - confirm: Confirm the decision and proceed
    - reject: Reject the decision
    - clarify: Provide clarification answers or inputs
    - override: Override the selected playbook
    """
    try:
        store = MindscapeStore()

        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        # Get IntentLog
        intent_log = await asyncio.to_thread(store.get_intent_log, card_id)
        if not intent_log:
            raise HTTPException(
                status_code=404, detail=f"Decision card {card_id} not found"
            )

        # Verify workspace match
        if intent_log.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403,
                detail="Decision card does not belong to this workspace",
            )

        final_decision = intent_log.final_decision or {}

        # Build user_override based on action
        user_override: Dict[str, Any] = {}

        if request.action == "confirm":
            user_override["confirmed"] = True
            user_override["confirmed_at"] = _utc_now().isoformat()
            if request.comment:
                user_override["comment"] = request.comment

            # If can_auto_execute, trigger execution
            if final_decision.get("can_auto_execute", False):
                playbook_code = final_decision.get("selected_playbook_code")
                if playbook_code:
                    try:
                        from backend.app.services.playbook_service import (
                            PlaybookService,
                            ExecutionMode,
                        )

                        playbook_service = PlaybookService()

                        # Get playbook inputs from final_decision or intent_log
                        playbook_inputs = final_decision.get(
                            "playbook_contribution", {}
                        ).get("inputs", {})
                        if not playbook_inputs:
                            # Fallback: try to extract from intent_log metadata or pipeline_steps
                            playbook_inputs = intent_log.metadata.get(
                                "playbook_inputs", {}
                            )

                        # Merge with user-provided inputs if any
                        if request.providedInputs:
                            playbook_inputs.update(request.providedInputs)

                        # Trigger execution
                        execution_result = await playbook_service.execute_playbook(
                            playbook_code=playbook_code,
                            workspace_id=workspace_id,
                            profile_id=intent_log.profile_id,
                            inputs=playbook_inputs,
                            execution_mode=ExecutionMode.ASYNC,
                            locale="zh-TW",
                            project_id=intent_log.project_id,
                        )

                        logger.info(
                            f"Decision {card_id} confirmed, triggered execution: {execution_result.execution_id}"
                        )
                        user_override["execution_id"] = execution_result.execution_id
                    except Exception as e:
                        logger.error(
                            f"Failed to trigger auto-execution for decision {card_id}: {e}",
                            exc_info=True,
                        )
                        # Don't fail the request, just log the error
                        user_override["execution_error"] = str(e)
                else:
                    logger.warning(
                        f"Decision {card_id} confirmed but no playbook_code in final_decision"
                    )

        elif request.action == "reject":
            user_override["rejected"] = True
            user_override["rejected_at"] = _utc_now().isoformat()
            if request.comment:
                user_override["rejection_reason"] = request.comment

        elif request.action == "clarify":
            if request.clarificationAnswers:
                user_override["clarification_answers"] = request.clarificationAnswers
            if request.providedInputs:
                user_override["provided_inputs"] = request.providedInputs
            user_override["clarified_at"] = _utc_now().isoformat()

            # Re-evaluate decision with new inputs
            # Note: This requires re-running the decision coordinator, which may be expensive
            # For now, we just update the override and let the next message trigger re-evaluation
            logger.info(
                f"Decision {card_id} clarified, user override stored. Next message will trigger re-evaluation."
            )

        elif request.action == "override":
            if not request.overridePlaybookCode:
                raise HTTPException(
                    status_code=400,
                    detail="overridePlaybookCode is required for override action",
                )

            user_override["override_playbook_code"] = request.overridePlaybookCode
            user_override["override_reason"] = request.overrideReason or "User override"
            user_override["overridden_at"] = _utc_now().isoformat()

            # If user wants to execute the overridden playbook immediately
            # (This is optional - user can also just update the decision and let next message trigger execution)
            playbook_code = request.overridePlaybookCode
            try:
                from backend.app.services.playbook_service import (
                    PlaybookService,
                    ExecutionMode,
                )

                playbook_service = PlaybookService()

                # Get playbook inputs (use provided inputs or fallback to original)
                playbook_inputs = {}
                if request.providedInputs:
                    playbook_inputs = request.providedInputs
                else:
                    playbook_inputs = final_decision.get(
                        "playbook_contribution", {}
                    ).get("inputs", {})

                # Trigger execution with overridden playbook
                execution_result = await playbook_service.execute_playbook(
                    playbook_code=playbook_code,
                    workspace_id=workspace_id,
                    profile_id=intent_log.profile_id,
                    inputs=playbook_inputs,
                    execution_mode=ExecutionMode.ASYNC,
                    locale="zh-TW",
                    project_id=intent_log.project_id,
                )

                logger.info(
                    f"Decision {card_id} overridden to {playbook_code}, triggered execution: {execution_result.execution_id}"
                )
                user_override["execution_id"] = execution_result.execution_id
            except Exception as e:
                logger.error(
                    f"Failed to trigger execution for overridden playbook {playbook_code}: {e}",
                    exc_info=True,
                )
                # Don't fail the request, just log the error
                user_override["execution_error"] = str(e)

        else:
            raise HTTPException(
                status_code=400, detail=f"Invalid action: {request.action}"
            )

        # Update IntentLog with user_override
        updated_log = await asyncio.to_thread(
            store.update_intent_log_override, card_id, user_override
        )
        if not updated_log:
            raise HTTPException(status_code=500, detail="Failed to update decision")

        # Emit event for UI update
        try:
            from backend.app.models.mindscape import MindEvent, EventType, EventActor

            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.USER,
                channel="api",
                profile_id=intent_log.profile_id,
                project_id=intent_log.project_id,
                workspace_id=workspace_id,
                event_type=EventType.DECISION_REQUIRED,  # Same type, but with updated status
                payload={
                    "decision_id": final_decision.get("decision_id", card_id),
                    "intent_log_id": card_id,
                    "action": request.action,
                    "status": (
                        "confirmed"
                        if request.action == "confirm"
                        else "rejected" if request.action == "reject" else "updated"
                    ),
                },
                entity_ids={
                    "decision_id": final_decision.get("decision_id", card_id),
                    "intent_log_id": card_id,
                },
            )
            await asyncio.to_thread(store.create_event, event)
        except Exception as e:
            logger.warning(f"Failed to emit decision update event: {e}")

        return {
            "success": True,
            "decision_id": final_decision.get("decision_id", card_id),
            "action": request.action,
            "updated_at": (
                updated_log.timestamp.isoformat()
                if isinstance(updated_log.timestamp, datetime)
                else updated_log.timestamp
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm decision: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to confirm decision: {str(e)}"
        )


@router.post("/{workspace_id}/decision-cards/{card_id}/assign")
async def assign_decision_card(
    workspace_id: str = Path(..., description="Workspace ID"),
    card_id: str = Path(..., description="Decision card ID"),
    assignee: Optional[str] = Body(None, description="Assignee user ID"),
    watchers: Optional[list[str]] = Body(None, description="Watcher user IDs"),
):
    """
    Assign a decision card to a user or add watchers
    """
    try:
        store = MindscapeStore()

        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        # Get IntentLog
        intent_log = await asyncio.to_thread(store.get_intent_log, card_id)
        if not intent_log:
            raise HTTPException(
                status_code=404, detail=f"Decision card {card_id} not found"
            )

        # Update metadata with assignment
        metadata = intent_log.metadata or {}
        if assignee:
            metadata["assignee"] = assignee
        if watchers:
            metadata["watchers"] = watchers

        # Update IntentLog metadata
        # Note: update_intent_log_override only updates user_override, not metadata
        # We need to update the log directly or add a new method
        # For now, store in user_override as a workaround
        user_override = intent_log.user_override or {}
        user_override["assignment"] = {
            "assignee": assignee,
            "watchers": watchers,
            "assigned_at": _utc_now().isoformat(),
        }

        updated_log = await asyncio.to_thread(
            store.update_intent_log_override, card_id, user_override
        )
        if not updated_log:
            raise HTTPException(status_code=500, detail="Failed to assign decision")

        return {
            "success": True,
            "decision_id": card_id,
            "assignee": assignee,
            "watchers": watchers,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign decision: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to assign decision: {str(e)}"
        )


# ==================== Break-glass Endpoints ====================


class BreakGlassRequestModel(BaseModel):
    """Request for break-glass permission"""

    operations: list[str] = Field(
        ..., description="Operations: read_file, write_file, execute_command, etc."
    )
    resource_patterns: list[str] = Field(..., description="Resource patterns to access")
    reason: str = Field(..., description="Why break-glass is needed")
    task_description: str = Field("", description="Task requiring break-glass")
    duration_minutes: int = Field(15, ge=5, le=60, description="Duration (5-60 min)")
    agent_id: Optional[str] = Field(
        None, description="Agent requesting (default: workspace.preferred_agent)"
    )


class BreakGlassApprovalModel(BaseModel):
    """Approve/deny break-glass request"""

    approved: bool
    comment: Optional[str] = None
    modified_operations: Optional[list[str]] = None
    modified_duration: Optional[int] = None


@router.post("/{workspace_id}/break-glass/request")
async def request_break_glass(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: BreakGlassRequestModel = Body(...),
):
    """
    Request break-glass permission for host access.

    Creates a Decision Card requiring user approval.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            BreakGlassService,
            BreakGlassRequest,
            get_break_glass_service,
        )

        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        agent_id = request.agent_id or getattr(workspace, "preferred_agent", None)
        if not agent_id:
            raise HTTPException(
                status_code=400,
                detail="agent_id required (workspace has no preferred_agent)",
            )

        service = get_break_glass_service()
        permission = await asyncio.to_thread(
            service.request_permission,
            BreakGlassRequest(
                workspace_id=workspace_id,
                agent_id=agent_id,
                operations=request.operations,
                resource_patterns=request.resource_patterns,
                reason=request.reason,
                task_description=request.task_description,
                duration_minutes=request.duration_minutes,
            ),
        )

        return {
            "success": True,
            "permission_id": permission.permission_id,
            "status": permission.status.value,
            "decision_card_id": permission.decision_card_id,
            "message": "Break-glass request created. Awaiting approval.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to request break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/break-glass/{permission_id}/approve")
async def approve_break_glass(
    workspace_id: str = Path(..., description="Workspace ID"),
    permission_id: str = Path(..., description="Permission ID"),
    request: BreakGlassApprovalModel = Body(...),
    approved_by: str = Query("user", description="Approving user ID"),
):
    """
    Approve or deny a break-glass request.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            BreakGlassApproval,
            get_break_glass_service,
        )

        service = get_break_glass_service()

        permission = await asyncio.to_thread(
            service.approve_permission,
            BreakGlassApproval(
                permission_id=permission_id,
                approved=request.approved,
                approved_by=approved_by,
                comment=request.comment,
                modified_operations=request.modified_operations,
                modified_duration=request.modified_duration,
            ),
        )

        if not permission:
            raise HTTPException(
                status_code=404, detail="Permission not found or not pending"
            )

        return {
            "success": True,
            "permission_id": permission.permission_id,
            "status": permission.status.value,
            "approved": request.approved,
            "expires_at": (
                permission.expires_at.isoformat() if permission.expires_at else None
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/break-glass")
async def list_break_glass_permissions(
    workspace_id: str = Path(..., description="Workspace ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """
    List break-glass permissions for a workspace.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            BreakGlassStatus,
            get_break_glass_service,
        )

        service = get_break_glass_service()

        status_filter = None
        if status:
            try:
                status_filter = BreakGlassStatus(status)
            except ValueError:
                pass

        permissions = await asyncio.to_thread(
            service.list_permissions, workspace_id, status_filter
        )

        return {
            "permissions": [
                {
                    "permission_id": p.permission_id,
                    "agent_id": p.agent_id,
                    "status": p.status.value,
                    "operations": [op.value for op in p.operations],
                    "resource_patterns": p.resource_patterns,
                    "reason": p.reason,
                    "created_at": p.created_at.isoformat(),
                    "expires_at": p.expires_at.isoformat() if p.expires_at else None,
                    "approved_by": p.approved_by,
                }
                for p in permissions
            ],
            "total": len(permissions),
        }

    except Exception as e:
        logger.error(f"Failed to list break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/break-glass/{permission_id}")
async def revoke_break_glass(
    workspace_id: str = Path(..., description="Workspace ID"),
    permission_id: str = Path(..., description="Permission ID"),
    revoked_by: str = Query("user", description="Revoking user ID"),
    reason: str = Query("", description="Reason for revocation"),
):
    """
    Revoke an active break-glass permission.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            get_break_glass_service,
        )

        service = get_break_glass_service()
        permission = await asyncio.to_thread(
            service.revoke_permission, permission_id, revoked_by, reason
        )

        if not permission:
            raise HTTPException(status_code=404, detail="Permission not found")

        return {
            "success": True,
            "permission_id": permission_id,
            "status": permission.status.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
