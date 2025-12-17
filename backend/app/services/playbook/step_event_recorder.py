"""
Step Event Recorder
Handles recording and updating playbook step events
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.services.stores.tool_calls_store import ToolCallsStore

logger = logging.getLogger(__name__)


class StepEventRecorder:
    """Handles recording and updating playbook step events"""

    def __init__(
        self,
        store: Any,
        workflow_tracker: WorkflowTracker,
        tool_calls_store: ToolCallsStore,
        state_store: Any
    ):
        self.store = store
        self.workflow_tracker = workflow_tracker
        self.tool_calls_store = tool_calls_store
        self.state_store = state_store

    def calculate_total_steps(
        self,
        execution_id: str,
        workspace_id: str,
        current_step_index: int,
        playbook_json: Optional[Any] = None,
        playbook_sop_content: Optional[str] = None,
        playbook_code: Optional[str] = None
    ) -> int:
        """
        Calculate total_steps for the execution.

        Args:
            execution_id: Execution ID
            workspace_id: Workspace ID
            current_step_index: Current step index (0-based)
            playbook_json: Playbook JSON object (optional)
            playbook_sop_content: Playbook SOP content (optional)
            playbook_code: Playbook code (optional)

        Returns:
            Total number of steps
        """
        try:
            existing_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=200
            )
            existing_steps = [
                e for e in existing_events
                if e.event_type == EventType.PLAYBOOK_STEP
                and isinstance(e.payload, dict)
                and e.payload.get('execution_id') == execution_id
            ]
            # Total steps is the maximum of:
            # Current step_index + 1 (which is the step we're about to create)
            # Number of existing steps + 1 (for the new step we're creating)
            dynamic_total_steps = max(current_step_index + 1, len(existing_steps) + 1)

            # Use dynamic total_steps for conversation mode
            # If playbook_json exists, use max of JSON steps and dynamic steps
            if playbook_json and playbook_json.steps:
                total_steps = max(len(playbook_json.steps), dynamic_total_steps)
                logger.info(f"StepEventRecorder: Using max of JSON steps ({len(playbook_json.steps)}) and dynamic steps ({dynamic_total_steps}) for playbook {playbook_code}")
            else:
                total_steps = dynamic_total_steps
                logger.info(f"StepEventRecorder: Using dynamic total_steps={total_steps} for conversation mode playbook {playbook_code}")
        except Exception as e:
            logger.warning(f"Failed to calculate dynamic total_steps: {e}")
            # Fallback: If not available from JSON, calculate from SOP phases
            if playbook_sop_content:
                calculated_steps = len(re.findall(r"### Phase \d:", playbook_sop_content))
                if calculated_steps > 0:
                    total_steps = calculated_steps
                    logger.info(f"StepEventRecorder: Calculated total_steps={total_steps} from SOP phases for playbook {playbook_code}")
                else:
                    total_steps = current_step_index + 1
            else:
                total_steps = current_step_index + 1

        return total_steps

    def record_assistant_message(
        self,
        execution_id: str,
        profile_id: str,
        workspace_id: str,
        playbook_code: Optional[str],
        assistant_response: str,
        project_id: Optional[str] = None
    ):
        """Record assistant message event"""
        try:
            import uuid
            message_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.ASSISTANT,
                channel="playbook",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "execution_id": execution_id,
                    "playbook_code": playbook_code,
                    "message": assistant_response[:500],
                    "role": "assistant"
                },
                entity_ids=[project_id] if project_id else [],
                metadata={}
            )
            self.store.create_event(message_event)
        except Exception as e:
            logger.warning(f"Failed to record assistant message event: {e}")

    def update_previous_step_status(
        self,
        execution_id: str,
        workspace_id: str,
        step_index: int
    ):
        """Update previous step status to completed"""
        if step_index <= 1:
            return

        try:
            previous_step_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=100
            )
            previous_step_event = None
            for event in previous_step_events:
                if (event.event_type == EventType.PLAYBOOK_STEP and
                    isinstance(event.payload, dict) and
                    event.payload.get('execution_id') == execution_id and
                    event.payload.get('step_index') == step_index - 1):
                    previous_step_event = event
                    break

            if previous_step_event and isinstance(previous_step_event.payload, dict):
                # Update previous step status to completed
                updated_payload = previous_step_event.payload.copy()
                updated_payload['status'] = 'completed'
                updated_payload['completed_at'] = datetime.utcnow().isoformat()
                # Update the event in the store
                self.store.update_event(
                    event_id=previous_step_event.id,
                    payload=updated_payload
                )
        except Exception as e:
            logger.warning(f"Failed to update previous step status: {e}")

    def update_all_previous_steps_total_steps(
        self,
        execution_id: str,
        workspace_id: str,
        total_steps: int,
        current_step_event_id: str
    ):
        """Update all previous steps' total_steps to match current total"""
        try:
            existing_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=200
            )
            all_step_events = [
                e for e in existing_events
                if e.event_type == EventType.PLAYBOOK_STEP
                and isinstance(e.payload, dict)
                and e.payload.get('execution_id') == execution_id
                and e.id != current_step_event_id  # Exclude the current step
            ]
            for prev_event in all_step_events:
                if isinstance(prev_event.payload, dict):
                    updated_payload = prev_event.payload.copy()
                    updated_payload['total_steps'] = total_steps
                    self.store.update_event(
                        event_id=prev_event.id,
                        payload=updated_payload
                    )
        except Exception as e:
            logger.warning(f"Failed to update previous steps' total_steps: {e}")

    def record_initial_step(
        self,
        execution_id: str,
        profile_id: str,
        workspace_id: str,
        playbook_code: str,
        conv_manager: Any,
        assistant_response: str,
        playbook_json: Optional[Any] = None,
        playbook: Optional[Any] = None,
        project_id: Optional[str] = None
    ) -> tuple[Any, int]:
        """
        Record initial step event for playbook execution.

        Returns:
            Tuple of (step_event, total_steps)
        """
        import uuid

        try:
            # Determine step information
            step_index = conv_manager.current_step  # This is 0 initially
            step_name = f"Step {step_index + 1}"  # Use 1-based naming for display
            step_type = "agent_action"
            agent_type = playbook.metadata.entry_agent_type if playbook and playbook.metadata else None

            # Generate log_summary from assistant response
            log_summary = f"Step {step_index + 1}: {assistant_response[:100]}..." if assistant_response else f"Step {step_index + 1}: Executing"

            # Record playbook step with full payload using WorkflowTracker
            step_event = self.workflow_tracker.create_playbook_step_event(
                execution_id=execution_id,
                step_index=step_index + 1,  # Use 1-based index for display
                step_name=step_name,
                status="completed",  # Initial step is completed when LLM responds
                step_type=step_type,
                agent_type=agent_type,
                used_tools=[],
                description=assistant_response[:500] if assistant_response else None,
                log_summary=log_summary,
                workspace_id=workspace_id,
                profile_id=profile_id,
                playbook_code=playbook_code
            )

            # Calculate total_steps
            playbook_sop_content = playbook.sop_content if playbook else None
            total_steps = self.calculate_total_steps(
                execution_id=execution_id,
                workspace_id=workspace_id,
                current_step_index=step_index,
                playbook_json=playbook_json,
                playbook_sop_content=playbook_sop_content,
                playbook_code=playbook_code
            )

            # Update step event with completed_at timestamp and total_steps
            if step_event and isinstance(step_event.payload, dict):
                step_event.payload["completed_at"] = datetime.utcnow().isoformat()
                step_event.payload["total_steps"] = total_steps
                self.store.update_event(
                    event_id=step_event.id,
                    payload=step_event.payload
                )

            # Update Task's execution_context with current step information
            if workspace_id:
                # step_index is 0-based here (from conv_manager.current_step), convert to 1-based for update
                self.state_store.update_task_step_info(
                    execution_id=execution_id,
                    step_index=step_index + 1,  # Convert 0-based to 1-based
                    total_steps=total_steps,
                    playbook_code=playbook_code
                )

            # Increment current_step for next interaction
            conv_manager.current_step += 1

            return step_event, total_steps

        except Exception as e:
            logger.warning(f"Failed to record initial playbook step event: {e}")
            return None, 1

    def record_continuation_step(
        self,
        execution_id: str,
        profile_id: str,
        workspace_id: str,
        playbook_code: str,
        conv_manager: Any,
        assistant_response: str,
        used_tools: List[str],
        existing_events: Optional[List[Any]] = None,
        project_id: Optional[str] = None,
        is_complete: bool = False
    ) -> tuple[Any, int]:
        """
        Record continuation step event for playbook execution.

        Returns:
            Tuple of (step_event, total_steps)
        """
        import uuid

        try:
            # Increment current step index before creating step event
            # This ensures step_index is 1-based and sequential
            conv_manager.current_step += 1
            step_index = conv_manager.current_step

            # Calculate total steps
            if existing_events is None:
                existing_events = self.store.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=200
                )
            existing_steps = [
                e for e in existing_events
                if e.event_type == EventType.PLAYBOOK_STEP
                and isinstance(e.payload, dict)
                and e.payload.get('execution_id') == execution_id
            ]
            # Total steps is the maximum of:
            # Current step_index (which is the step we're about to create)
            # Number of existing steps + 1 (for the new step we're creating)
            total_steps = max(step_index, len(existing_steps) + 1)

            # Record assistant message
            self.record_assistant_message(
                execution_id=execution_id,
                profile_id=profile_id,
                workspace_id=workspace_id,
                playbook_code=playbook_code,
                assistant_response=assistant_response,
                project_id=project_id
            )

            # Determine step information
            step_name = f"Step {step_index}"
            step_type = "agent_action"  # Default, could be determined from playbook SOP
            agent_type = None  # Could be determined from playbook or response

            # Generate log_summary
            log_summary = f"Step {step_index}: {assistant_response[:100]}..." if assistant_response else f"Step {step_index}: Executing"

            # Update previous step status
            self.update_previous_step_status(
                execution_id=execution_id,
                workspace_id=workspace_id,
                step_index=step_index
            )

            # Determine step status based on completion state
            # If step is not complete, it means we're waiting for user input/confirmation
            step_status = "completed" if is_complete else "waiting_confirmation"

            # Record playbook step with full payload using WorkflowTracker
            step_event = self.workflow_tracker.create_playbook_step_event(
                execution_id=execution_id,
                step_index=step_index,
                step_name=step_name,
                status=step_status,  # Use waiting_confirmation if step is not complete
                step_type=step_type,
                agent_type=agent_type,
                used_tools=used_tools,
                description=assistant_response[:500] if assistant_response else None,
                log_summary=log_summary,
                workspace_id=workspace_id,
                profile_id=profile_id,
                playbook_code=playbook_code
            )

            # Update step event payload to include total_steps for frontend display
            if step_event and isinstance(step_event.payload, dict):
                step_event.payload['total_steps'] = total_steps
                self.store.update_event(
                    event_id=step_event.id,
                    payload=step_event.payload
                )

                # Update all previous steps' total_steps to match current total
                self.update_all_previous_steps_total_steps(
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    total_steps=total_steps,
                    current_step_event_id=step_event.id
                )

            # Update Task's execution_context with current step information
            self.state_store.update_task_step_info(
                execution_id=execution_id,
                step_index=step_index,  # step_index is 1-based
                total_steps=total_steps,
                playbook_code=playbook_code
            )

            # Update step event with actual tools used in this step
            self._update_step_event_with_tools(step_event, execution_id, log_summary)

            return step_event, total_steps

        except Exception as e:
            logger.warning(f"Failed to record continuation playbook step event: {e}")
            return None, 1

    def _update_step_event_with_tools(
        self,
        step_event: Any,
        execution_id: str,
        log_summary: str
    ):
        """Update step event with actual tools used"""
        try:
            tool_calls = self.tool_calls_store.list_tool_calls(
                execution_id=execution_id,
                step_id=step_event.id,
                limit=100
            )
            if tool_calls:
                # Get unique tool names from tool calls
                used_tools = list(set([tc.tool_name for tc in tool_calls if tc.tool_name]))
                # Update step event with actual tools
                self.workflow_tracker.update_playbook_step_event(
                    step_event_id=step_event.id,
                    log_summary=log_summary
                )
                # Update payload with used_tools
                step_event.payload["used_tools"] = used_tools
                self.store.update_event(step_event)
        except Exception as e:
            logger.warning(f"Failed to update step event with tool calls: {e}")

    def finalize_step_with_output(
        self,
        step_event: Any,
        execution_id: str,
        structured_output: Dict[str, Any]
    ):
        """Finalize step event with structured output (embedding, StageResult)"""
        if not step_event or not structured_output:
            return

        try:
            # Generate embedding for completed steps with structured output
            step_event.metadata.update({
                "has_structured_output": True,
                "should_embed": True,
                "is_artifact": True
            })
            self.store.update_event(step_event)
            # Generate embedding if needed
            if hasattr(self.store, 'generate_embedding'):
                self.store.generate_embedding(step_event)

            # Create StageResult if we have structured output using WorkflowTracker
            step_event_id = step_event.id
            self.workflow_tracker.create_stage_result(
                execution_id=execution_id,
                step_id=step_event_id,
                stage_name="final_output",
                result_type="draft",  # Could be determined from playbook or output structure
                content=structured_output,
                preview=str(structured_output)[:200] if structured_output else None,
                requires_review=False
            )
        except Exception as e:
            logger.warning(f"Failed to finalize step event with output: {e}")

