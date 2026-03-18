"""
Tool Event Reporter
Handles tracking, MindEvents, and State Integration for tool execution.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.core.state.state_integration import StateIntegrationAdapter
from backend.app.core.trace import TraceStatus, TraceNodeType, get_trace_recorder

logger = logging.getLogger(__name__)

def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

class ToolEventReporter:
    """Handles logging tool events, traces, and state integration."""

    def __init__(self, store: MindscapeStore, workflow_tracker: WorkflowTracker):
        self.store = store
        self.workflow_tracker = workflow_tracker
        self.state_adapter = StateIntegrationAdapter()
        
    def start_trace_node(self, tool_fqn: str, kwargs: Dict[str, Any], tool_slot: Optional[str], factory_cluster: str, step_id: Optional[str], execution_id: Optional[str], workspace_id: Optional[str], execution_context: Dict[str, Any]) -> Optional[str]:
        if not (execution_id and workspace_id):
            return None
            
        try:
            trace_recorder = get_trace_recorder()
            trace_id = execution_context.get("trace_id")
            if not trace_id:
                trace_id = trace_recorder.create_trace(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    user_id=execution_context.get("user_id"),
                )
                execution_context["trace_id"] = trace_id

            trace_node_id = trace_recorder.start_node(
                trace_id=trace_id,
                node_type=TraceNodeType.TOOL,
                name=f"tool:{tool_fqn}",
                input_data={
                    "tool_fqn": tool_fqn,
                    "tool_slot": tool_slot,
                    "parameters": {k: str(v)[:200] for k, v in kwargs.items()},
                },
                metadata={
                    "factory_cluster": factory_cluster,
                    "step_id": step_id,
                },
            )
            return trace_node_id
        except Exception as e:
            logger.warning(f"Failed to start trace node for tool execution: {e}")
            return None

    def record_tool_start(self, tool_fqn: str, kwargs: Dict[str, Any], factory_cluster: str, step_id: Optional[str], execution_id: Optional[str]):
        if not execution_id:
            return None
        try:
            return self.workflow_tracker.record_tool_call_start(
                execution_id=execution_id,
                step_id=step_id or "",
                tool_name=tool_fqn,
                parameters=kwargs,
                factory_cluster=factory_cluster,
            )
        except Exception as e:
            logger.warning(f"Failed to create ToolCall record: {e}")
            return None

    def integrate_state(self, tool_fqn: str, tool_slot: Optional[str], result: Any, execution_id: Optional[str], workspace_id: Optional[str], step_id: Optional[str], tool_start_time: datetime):
        try:
            world_entry = self.state_adapter.tool_result_to_world_state(
                workspace_id=workspace_id or "",
                tool_id=tool_fqn,
                tool_slot=tool_slot,
                result=result,
                execution_id=execution_id,
                metadata={
                    "duration_ms": int((_utc_now() - tool_start_time).total_seconds() * 1000),
                    "step_id": step_id,
                },
            )
            logger.debug(f"PlaybookToolExecutor: Converted tool result to WorldStateEntry (entry_id={world_entry.entry_id})")
        except Exception as e:
            logger.warning(f"Failed to integrate tool result to WorldState: {e}", exc_info=True)

    def end_trace_node(self, trace_node_id: str, result: Any, duration_ms: int, execution_id: Optional[str], workspace_id: Optional[str], execution_context: Dict[str, Any]):
        if trace_node_id and execution_id and workspace_id:
            try:
                trace_recorder = get_trace_recorder()
                trace_id = execution_context.get("trace_id")
                if trace_id:
                    trace_recorder.end_node(
                        trace_id=trace_id,
                        node_id=trace_node_id,
                        status=TraceStatus.SUCCESS,
                        output_data={"result": str(result)[:1000] if result else None},
                        latency_ms=duration_ms,
                    )
            except Exception as e:
                logger.warning(f"Failed to end trace node for tool execution: {e}")

    def emit_mind_event(
        self,
        tool_fqn: str,
        kwargs: Dict[str, Any],
        factory_cluster: str,
        tool_call_id: str,
        result: Any,
        duration_seconds: float,
        profile_id: Optional[str],
        project_id: Optional[str],
        workspace_id: Optional[str],
        execution_id: Optional[str],
        step_id: Optional[str],
    ):
        if not profile_id:
            return
            
        try:
            tool_end_time = _utc_now()
            # CALL Event
            call_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=tool_end_time,
                actor=EventActor.ASSISTANT,
                channel="playbook",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.TOOL_CALL,
                payload={
                    "tool_fqn": tool_fqn,
                    "tool_call_id": tool_call_id,
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "status": "completed",
                    "duration_seconds": duration_seconds,
                },
                entity_ids=[project_id] if project_id else [],
                metadata={
                    "tool_params": {k: str(v)[:100] for k, v in kwargs.items() if k != "project_id"},
                    "factory_cluster": factory_cluster,
                },
            )
            self.store.create_event(call_event)

            # RESULT Event
            result_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=tool_end_time,
                actor=EventActor.SYSTEM,
                channel="playbook",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.TOOL_RESULT,
                payload={
                    "tool_fqn": tool_fqn,
                    "tool_call_id": tool_call_id,
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "result_summary": str(result)[:500] if result else None,
                },
                entity_ids=[project_id] if project_id else [],
                metadata={"factory_cluster": factory_cluster},
            )
            self.store.create_event(result_event)
        except Exception as e:
            logger.warning(f"Failed to record tool MindEvents: {e}")

    def record_tool_complete(self, tool_call, result: Any, execution_id: Optional[str]):
        if execution_id and tool_call:
            try:
                self.workflow_tracker.record_tool_call_complete(
                    tool_call_id=tool_call.id,
                    response={"result": str(result)[:1000]} if result else {"result": result},
                )
            except Exception as e:
                logger.warning(f"Failed to update ToolCall record: {e}")
