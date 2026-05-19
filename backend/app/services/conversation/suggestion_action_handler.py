"""Suggestion action handler facade."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...core.domain_context import LocalDomainContext
from ...services.intent_infra import IntentInfraService
from ...services.mindscape_store import MindscapeStore
from ...services.playbook_service import PlaybookService
from .suggestion_action_handler_core import (
    create_user_event,
    handle_add_to_mindscape,
    handle_create_intent,
    handle_error,
)
from .suggestion_action_handler_core.dispatch import (
    handle_action as handle_action_helper,
    handle_suggestion_action_with_ctx as handle_suggestion_action_with_ctx_helper,
)
from .suggestion_action_handler_core.pack_execution import (
    handle_execute_pack as handle_execute_pack_helper,
)
from .suggestion_action_handler_core.plan_fallback import (
    execute_via_plan as execute_via_plan_helper,
)
from .suggestion_action_handler_core.playbook_tool_actions import (
    build_object_action_dispatch_metadata as build_object_action_dispatch_metadata_helper,
    handle_execute_playbook as handle_execute_playbook_helper,
    handle_use_tool as handle_use_tool_helper,
)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _build_object_action_dispatch_metadata(
    *,
    action_params: Dict[str, Any],
    execution_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build object-action dispatch metadata for compatibility callers."""
    return build_object_action_dispatch_metadata_helper(
        action_params=action_params,
        execution_id=execution_id,
    )


class SuggestionActionHandler:
    """Handles actions from dynamic suggestions."""

    def __init__(
        self,
        store: MindscapeStore,
        playbook_runner,
        task_manager,
        execution_coordinator=None,
        default_locale: str = "en",
        playbook_service: Optional[PlaybookService] = None,
        intent_infra: Optional[IntentInfraService] = None,
    ):
        """Initialize SuggestionActionHandler."""
        self.store = store
        self.playbook_runner = playbook_runner
        self.task_manager = task_manager
        self.execution_coordinator = execution_coordinator
        self.playbook_service = playbook_service or PlaybookService(store=store)
        self.intent_infra = intent_infra or IntentInfraService(
            store=store,
            default_locale=default_locale,
        )
        self.default_locale = default_locale

    async def handle_action(
        self,
        workspace_id: str,
        profile_id: str,
        action: str,
        action_params: Dict[str, Any],
        project_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle action from dynamic suggestion."""
        return await handle_action_helper(
            self,
            workspace_id=workspace_id,
            profile_id=profile_id,
            action=action,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id,
        )

    async def handle_suggestion_action_with_ctx(
        self,
        ctx: LocalDomainContext,
        suggestion_id: Optional[str],
        action: str,
        action_params: Dict[str, Any],
        project_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle action from dynamic suggestion using execution context."""
        return await handle_suggestion_action_with_ctx_helper(
            self,
            ctx=ctx,
            suggestion_id=suggestion_id,
            action=action,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id,
        )

    async def _handle_execute_playbook(
        self,
        ctx: LocalDomainContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle execute_playbook action."""
        return await handle_execute_playbook_helper(
            self,
            ctx=ctx,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id,
        )

    async def _handle_use_tool(
        self,
        ctx: LocalDomainContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle use_tool action."""
        return await handle_use_tool_helper(
            self,
            ctx=ctx,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id,
        )

    async def _handle_add_to_mindscape(
        self,
        ctx: LocalDomainContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle add_to_mindscape action."""
        return handle_add_to_mindscape(
            store=self.store,
            default_locale=self.default_locale,
            ctx=ctx,
            action_params=action_params,
            message_id=message_id,
        )

    def _handle_create_intent(
        self,
        ctx: LocalDomainContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle create_intent action."""
        return handle_create_intent(
            store=self.store,
            default_locale=self.default_locale,
            ctx=ctx,
            action_params=action_params,
            project_id=project_id,
        )

    def _handle_start_chat(self, workspace_id: str) -> Dict[str, Any]:
        """Handle start_chat action."""
        return {"workspace_id": workspace_id, "action": "start_chat"}

    def _handle_upload_file(self, workspace_id: str) -> Dict[str, Any]:
        """Handle upload_file action."""
        return {"workspace_id": workspace_id, "action": "upload_file"}

    async def _handle_execute_pack(
        self,
        ctx: LocalDomainContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle execute_pack action."""
        return await handle_execute_pack_helper(
            self,
            ctx=ctx,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id,
        )

    def _handle_error(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        error_message: str,
    ) -> Dict[str, Any]:
        """Handle action errors."""
        return handle_error(
            store=self.store,
            default_locale=self.default_locale,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            error_message=error_message,
        )

    async def _execute_via_plan(
        self,
        pack_id: str,
        ctx: LocalDomainContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        task: Optional[Any],
        action_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute pack via ExecutionPlan fallback."""
        return await execute_via_plan_helper(
            self,
            pack_id=pack_id,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            task=task,
            action_params=action_params,
        )

    def _create_user_event(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        message: str,
        action: str,
        action_params: Dict[str, Any],
    ):
        """Create user message event for action."""
        create_user_event(
            store=self.store,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            message=message,
            action=action,
            action_params=action_params,
        )
