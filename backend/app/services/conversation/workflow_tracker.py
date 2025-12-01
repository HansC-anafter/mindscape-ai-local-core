"""
Workflow Tracker - Lightweight tracking helper for Playbook execution

Based on the "取長補短" (leverage strengths) design:
- ExecutionSession: Task view model (no separate table)
- ExecutionStep: MindEvent(PLAYBOOK_STEP) view model (no separate table)
- ToolCall: Independent table (for efficient querying)
- StageResult: Independent table (for efficient querying)
- Agent Collaboration: MindEvent(AGENT_EXECUTION) view model (no separate table)

This tracker provides helper methods to create and manage tracking records
without duplicating the view model logic (which is in workspace.py).
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from ..mindscape_store import MindscapeStore
from ...models.mindscape import MindEvent, EventType, EventActor
from ..stores.tool_calls_store import ToolCallsStore, ToolCall
from ..stores.stage_results_store import StageResultsStore, StageResult

logger = logging.getLogger(__name__)


class WorkflowTracker:
    """
    WorkflowTracker - Lightweight tracking helper for Playbook execution

    Provides helper methods to:
    - Create MindEvent(PLAYBOOK_STEP) records
    - Record ToolCall events
    - Record StageResult events
    - Track Agent Collaborations via MindEvent(AGENT_EXECUTION)

    Note: ExecutionSession and ExecutionStep are view models,
    built from Task and MindEvent respectively.
    """

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.tool_calls_store = ToolCallsStore(store.db_path)
        self.stage_results_store = StageResultsStore(store.db_path)

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
        playbook_code: Optional[str] = None
    ) -> MindEvent:
        """
        Create a PLAYBOOK_STEP MindEvent

        This event represents a single step in Playbook execution.
        It will be used to build ExecutionStep view model later.

        Args:
            execution_id: Execution ID (same as Task.id)
            step_index: Step index (0-based)
            step_name: Step name/description
            status: Step status: pending/running/completed/failed/waiting_confirmation
            step_type: Step type: agent_action/tool_call/agent_collaboration/user_confirmation
            agent_type: Agent type (e.g., 'researcher', 'editor')
            used_tools: List of tools used in this step
            description: Step description
            log_summary: Human-readable log summary
            assigned_agent: Assigned agent name
            collaborating_agents: List of collaborating agent names
            requires_confirmation: Whether this step requires user confirmation
            confirmation_prompt: Confirmation prompt text
            workspace_id: Workspace ID
            profile_id: Profile ID
            playbook_code: Playbook code

        Returns:
            Created MindEvent
        """
        step_event_id = str(uuid.uuid4())
        now = datetime.utcnow()

        payload = {
            "execution_id": execution_id,
            "step_index": step_index,
            "step_name": step_name,
            "status": status,
            "step_type": step_type,
            "agent_type": agent_type,
            "used_tools": used_tools or [],
            "description": description,
            "log_summary": log_summary,
            "assigned_agent": assigned_agent,
            "collaborating_agents": collaborating_agents or [],
            "requires_confirmation": requires_confirmation,
            "confirmation_prompt": confirmation_prompt,
            "confirmation_status": "pending" if requires_confirmation else None,
            "started_at": now.isoformat() if status in ["running", "completed"] else None,
            "completed_at": now.isoformat() if status == "completed" else None,
            "playbook_code": playbook_code
        }

        event = MindEvent(
            id=step_event_id,
            timestamp=now,
            actor=EventActor.SYSTEM,
            channel="workspace",
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_type=EventType.PLAYBOOK_STEP,
            payload=payload,
            entity_ids=[execution_id] if execution_id else [],
            metadata={
                "is_playbook_step": True,
                "playbook_code": playbook_code
            }
        )

        try:
            self.store.create_event(event)
            logger.debug(f"Created PLAYBOOK_STEP event: {step_event_id} for execution {execution_id}, step {step_index}")
        except Exception as e:
            logger.warning(f"Failed to create PLAYBOOK_STEP event: {e}")

        return event

    def update_playbook_step_event(
        self,
        step_event_id: str,
        status: Optional[str] = None,
        log_summary: Optional[str] = None,
        completed: bool = False,
        error: Optional[str] = None
    ) -> bool:
        """
        Update an existing PLAYBOOK_STEP MindEvent

        Args:
            step_event_id: MindEvent.id (PLAYBOOK_STEP event)
            status: New status (if provided)
            log_summary: Updated log summary (if provided)
            completed: Whether to mark as completed
            error: Error message if failed

        Returns:
            True if updated successfully
        """
        try:
            event = self.store.get_event(step_event_id)
            if not event or event.event_type != EventType.PLAYBOOK_STEP:
                logger.warning(f"Event {step_event_id} not found or not a PLAYBOOK_STEP event")
                return False

            payload = event.payload or {}
            if status:
                payload["status"] = status
            if log_summary:
                payload["log_summary"] = log_summary
            if error:
                payload["error"] = error
                payload["status"] = "failed"
            if completed:
                payload["status"] = "completed"
                payload["completed_at"] = datetime.utcnow().isoformat()

            event.payload = payload
            self.store.update_event(event)
            return True
        except Exception as e:
            logger.warning(f"Failed to update PLAYBOOK_STEP event: {e}")
            return False

    def record_tool_call_start(
        self,
        execution_id: str,
        step_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        factory_cluster: Optional[str] = None
    ) -> ToolCall:
        """
        Record a tool call start

        Args:
            execution_id: Execution ID
            step_id: Step ID (MindEvent.id)
            tool_name: Tool name (e.g., 'canva.create_design')
            parameters: Tool call parameters
            factory_cluster: Factory cluster (e.g., 'local_mcp', 'sem-hub')

        Returns:
            Created ToolCall record
        """
        tool_call_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Determine factory_cluster if not provided
        if not factory_cluster:
            if "mcp" in tool_name.lower() or tool_name.startswith("local_"):
                factory_cluster = "local_mcp"
            elif "sem-" in tool_name.lower():
                factory_cluster = "sem-hub"
            elif "wp" in tool_name.lower() or "wordpress" in tool_name.lower():
                factory_cluster = "wp-hub"
            elif "n8n" in tool_name.lower():
                factory_cluster = "n8n"
            else:
                factory_cluster = "local_mcp"  # default

        tool_call = ToolCall(
            id=tool_call_id,
            execution_id=execution_id,
            step_id=step_id,
            tool_name=tool_name,
            tool_id=None,
            parameters=parameters,
            response=None,
            status="pending",
            error=None,
            duration_ms=None,
            factory_cluster=factory_cluster,
            started_at=now,
            completed_at=None,
            created_at=now
        )

        try:
            self.tool_calls_store.create_tool_call(tool_call)
            logger.debug(f"Created ToolCall record: {tool_call_id} for tool {tool_name}")
        except Exception as e:
            logger.warning(f"Failed to create ToolCall record: {e}")

        return tool_call

    def record_tool_call_complete(
        self,
        tool_call_id: str,
        response: Dict[str, Any],
        duration_ms: Optional[int] = None
    ) -> bool:
        """
        Mark a tool call as completed

        Args:
            tool_call_id: ToolCall.id
            response: Tool response
            duration_ms: Call duration in milliseconds (optional, will be auto-calculated if not provided)

        Returns:
            True if updated successfully
        """
        try:
            # duration_ms is auto-calculated by update_tool_call_status based on started_at and completed_at
            return self.tool_calls_store.update_tool_call_status(
                tool_call_id=tool_call_id,
                status="completed",
                response=response,
                completed_at=datetime.utcnow()
            )
        except Exception as e:
            logger.warning(f"Failed to update ToolCall: {e}")
            return False

    def record_tool_call_fail(
        self,
        tool_call_id: str,
        error: str,
        duration_ms: Optional[int] = None
    ) -> bool:
        """
        Mark a tool call as failed

        Args:
            tool_call_id: ToolCall.id
            error: Error message
            duration_ms: Call duration in milliseconds (optional, will be auto-calculated if not provided)

        Returns:
            True if updated successfully
        """
        try:
            # duration_ms is auto-calculated by update_tool_call_status based on started_at and completed_at
            return self.tool_calls_store.update_tool_call_status(
                tool_call_id=tool_call_id,
                status="failed",
                error=error,
                completed_at=datetime.utcnow()
            )
        except Exception as e:
            logger.warning(f"Failed to update ToolCall: {e}")
            return False

    def create_stage_result(
        self,
        execution_id: str,
        step_id: str,
        stage_name: str,
        result_type: str,
        content: Dict[str, Any],
        preview: Optional[str] = None,
        requires_review: bool = False,
        artifact_id: Optional[str] = None
    ) -> StageResult:
        """
        Create a StageResult record for intermediate results

        Args:
            execution_id: Execution ID
            step_id: Step ID (MindEvent.id)
            stage_name: Stage name
            result_type: Result type: draft/analysis/design/data
            content: Result content (structured)
            preview: Human-readable preview text
            requires_review: Whether this result requires user review
            artifact_id: Associated artifact ID (if any)

        Returns:
            Created StageResult record
        """
        stage_result_id = str(uuid.uuid4())

        stage_result = StageResult(
            id=stage_result_id,
            execution_id=execution_id,
            step_id=step_id,
            stage_name=stage_name,
            result_type=result_type,
            content=content,
            preview=preview,
            requires_review=requires_review,
            review_status="pending" if requires_review else None,
            artifact_id=artifact_id,
            created_at=datetime.utcnow()
        )

        try:
            self.stage_results_store.create_stage_result(stage_result)
            logger.debug(f"Created StageResult: {stage_result_id} for stage {stage_name}")
        except Exception as e:
            logger.warning(f"Failed to create StageResult: {e}")

        return stage_result

    def create_agent_collaboration_event(
        self,
        execution_id: str,
        step_id: str,
        participants: List[str],
        topic: str,
        collaboration_type: str = "discussion",
        discussion: Optional[List[Dict[str, str]]] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> MindEvent:
        """
        Create an AGENT_EXECUTION MindEvent for agent collaboration

        Args:
            execution_id: Execution ID
            step_id: Step ID (MindEvent.id)
            participants: List of participant agent names
            topic: Collaboration topic
            collaboration_type: Collaboration type: discussion/review/planning
            discussion: Discussion messages (optional)
            workspace_id: Workspace ID
            profile_id: Profile ID

        Returns:
            Created MindEvent
        """
        collaboration_event_id = str(uuid.uuid4())
        now = datetime.utcnow()

        payload = {
            "execution_id": execution_id,
            "step_id": step_id,
            "collaboration_type": collaboration_type,
            "participants": participants,
            "topic": topic,
            "discussion": discussion or [],
            "status": "active",
            "started_at": now.isoformat()
        }

        event = MindEvent(
            id=collaboration_event_id,
            timestamp=now,
            actor=EventActor.SYSTEM,
            channel="workspace",
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_type=EventType.AGENT_EXECUTION,
            payload=payload,
            entity_ids=[execution_id] if execution_id else [],
            metadata={
                "is_agent_collaboration": True,
                "collaboration_type": collaboration_type
            }
        )

        try:
            self.store.create_event(event)
            logger.debug(f"Created AGENT_EXECUTION event: {collaboration_event_id} for collaboration: {topic}")
        except Exception as e:
            logger.warning(f"Failed to create AGENT_EXECUTION event: {e}")

        return event

    def update_agent_collaboration_event(
        self,
        collaboration_event_id: str,
        status: str = "completed",
        discussion: Optional[List[Dict[str, str]]] = None,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an AGENT_EXECUTION event (mark as completed, add discussion, etc.)

        Args:
            collaboration_event_id: MindEvent.id (AGENT_EXECUTION event)
            status: New status: active/completed/failed
            discussion: Additional discussion messages
            result: Collaboration result

        Returns:
            True if updated successfully
        """
        try:
            event = self.store.get_event(collaboration_event_id)
            if not event or event.event_type != EventType.AGENT_EXECUTION:
                logger.warning(f"Event {collaboration_event_id} not found or not an AGENT_EXECUTION event")
                return False

            payload = event.payload or {}
            payload["status"] = status
            if discussion:
                existing_discussion = payload.get("discussion", [])
                payload["discussion"] = existing_discussion + discussion
            if result:
                payload["result"] = result
            if status == "completed":
                payload["completed_at"] = datetime.utcnow().isoformat()

            event.payload = payload
            self.store.update_event(event)
            return True
        except Exception as e:
            logger.warning(f"Failed to update AGENT_EXECUTION event: {e}")
            return False

