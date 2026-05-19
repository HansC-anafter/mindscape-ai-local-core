"""
Workflow Tracker - Lightweight tracking helper for Playbook execution.

This tracker provides helper methods to create and manage tracking records
without duplicating the view model logic.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.conversation.workflow_tracker_core.agent_collaboration import (
    create_agent_collaboration_event,
    update_agent_collaboration_event,
)
from backend.app.services.conversation.workflow_tracker_core.clock import (
    utc_now as _utc_now,
)
from backend.app.services.conversation.workflow_tracker_core.playbook_steps import (
    create_playbook_step_event,
    update_playbook_step_event,
)
from backend.app.services.conversation.workflow_tracker_core.stage_results import (
    create_stage_result,
)
from backend.app.services.conversation.workflow_tracker_core.tool_calls import (
    record_tool_call_complete,
    record_tool_call_fail,
    record_tool_call_start,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.stage_results_store import (
    StageResult,
    StageResultsStore,
)
from backend.app.services.stores.tool_calls_store import ToolCall, ToolCallsStore

logger = logging.getLogger(__name__)


class WorkflowTracker:
    """
    WorkflowTracker - Lightweight tracking helper for Playbook execution.

    Provides helper methods to:
    - Create MindEvent(PLAYBOOK_STEP) records
    - Record ToolCall events
    - Record StageResult events
    - Track Agent Collaborations via MindEvent(AGENT_EXECUTION)
    """

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.tool_calls_store = ToolCallsStore()
        self.stage_results_store = StageResultsStore()

    def create_playbook_step_event(
        self,
        execution_id: str,
        step_index: int,
        step_name: str,
        status: str = "running",
        step_type: str = "agent_action",
        agent_type: Optional[str] = None,
        used_tools: Optional[List[str]] = None,
        description: Optional[str] = None,
        log_summary: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        collaborating_agents: Optional[List[str]] = None,
        requires_confirmation: bool = False,
        confirmation_prompt: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        playbook_code: Optional[str] = None,
    ) -> MindEvent:
        """Create a PLAYBOOK_STEP MindEvent."""
        return create_playbook_step_event(
            tracker=self,
            execution_id=execution_id,
            step_index=step_index,
            step_name=step_name,
            status=status,
            step_type=step_type,
            agent_type=agent_type,
            used_tools=used_tools,
            description=description,
            log_summary=log_summary,
            assigned_agent=assigned_agent,
            collaborating_agents=collaborating_agents,
            requires_confirmation=requires_confirmation,
            confirmation_prompt=confirmation_prompt,
            workspace_id=workspace_id,
            profile_id=profile_id,
            playbook_code=playbook_code,
        )

    def update_playbook_step_event(
        self,
        step_event_id: str,
        status: Optional[str] = None,
        log_summary: Optional[str] = None,
        completed: bool = False,
        error: Optional[str] = None,
    ) -> bool:
        """Update an existing PLAYBOOK_STEP MindEvent."""
        return update_playbook_step_event(
            tracker=self,
            step_event_id=step_event_id,
            status=status,
            log_summary=log_summary,
            completed=completed,
            error=error,
        )

    def record_tool_call_start(
        self,
        execution_id: str,
        step_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        factory_cluster: Optional[str] = None,
    ) -> ToolCall:
        """Record a tool call start."""
        return record_tool_call_start(
            tracker=self,
            execution_id=execution_id,
            step_id=step_id,
            tool_name=tool_name,
            parameters=parameters,
            factory_cluster=factory_cluster,
        )

    def record_tool_call_complete(
        self,
        tool_call_id: str,
        response: Dict[str, Any],
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Mark a tool call as completed."""
        return record_tool_call_complete(
            tracker=self,
            tool_call_id=tool_call_id,
            response=response,
            duration_ms=duration_ms,
        )

    def record_tool_call_fail(
        self,
        tool_call_id: str,
        error: str,
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Mark a tool call as failed."""
        return record_tool_call_fail(
            tracker=self,
            tool_call_id=tool_call_id,
            error=error,
            duration_ms=duration_ms,
        )

    def create_stage_result(
        self,
        execution_id: str,
        step_id: str,
        stage_name: str,
        result_type: str,
        content: Dict[str, Any],
        preview: Optional[str] = None,
        requires_review: bool = False,
        artifact_id: Optional[str] = None,
    ) -> StageResult:
        """Create a StageResult record for intermediate results."""
        return create_stage_result(
            tracker=self,
            execution_id=execution_id,
            step_id=step_id,
            stage_name=stage_name,
            result_type=result_type,
            content=content,
            preview=preview,
            requires_review=requires_review,
            artifact_id=artifact_id,
        )

    def create_agent_collaboration_event(
        self,
        execution_id: str,
        step_id: str,
        participants: List[str],
        topic: str,
        collaboration_type: str = "discussion",
        discussion: Optional[List[Dict[str, str]]] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> MindEvent:
        """Create an AGENT_EXECUTION MindEvent for agent collaboration."""
        return create_agent_collaboration_event(
            tracker=self,
            execution_id=execution_id,
            step_id=step_id,
            participants=participants,
            topic=topic,
            collaboration_type=collaboration_type,
            discussion=discussion,
            workspace_id=workspace_id,
            profile_id=profile_id,
        )

    def update_agent_collaboration_event(
        self,
        collaboration_event_id: str,
        status: str = "completed",
        discussion: Optional[List[Dict[str, str]]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update an AGENT_EXECUTION event."""
        return update_agent_collaboration_event(
            tracker=self,
            collaboration_event_id=collaboration_event_id,
            status=status,
            discussion=discussion,
            result=result,
        )
