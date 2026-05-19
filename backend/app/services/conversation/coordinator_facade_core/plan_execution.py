"""Plan execution delegation helpers for CoordinatorFacade."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter


async def execute_plan(
    *,
    facade: Any,
    execution_plan: Any,
    workspace_id: str,
    profile_id: str,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str] = None,
    task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute an execution plan after building the local domain context."""
    ctx = LocalDomainContext(
        actor_id=profile_id,
        workspace_id=workspace_id,
        tags={"mode": "local"},
    )
    return await facade.execute_plan_with_ctx(
        execution_plan=execution_plan,
        ctx=ctx,
        message_id=message_id,
        files=files,
        message=message,
        project_id=project_id,
        task_event_callback=task_event_callback,
    )


async def execute_plan_with_ctx(
    *,
    facade: Any,
    execution_plan: Any,
    ctx: LocalDomainContext,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str] = None,
    task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    prevent_suggestion_creation: bool = False,
) -> Dict[str, Any]:
    """Execute an execution plan through the split coordination modules."""
    await facade._resolve_mind_lens(execution_plan, ctx)
    event_emitter = TaskEventsEmitter(callback=task_event_callback)
    workspace = await facade.store.workspaces.get_workspace(ctx.workspace_id)

    return await facade.plan_executor.execute_plan(
        execution_plan=execution_plan,
        ctx=ctx,
        message_id=message_id,
        files=files,
        message=message,
        project_id=project_id,
        event_emitter=event_emitter,
        workspace=workspace,
        prevent_suggestion_creation=prevent_suggestion_creation,
        suggestion_creator=facade.suggestion_card_creator,
    )
