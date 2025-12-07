"""
Playbook Tool Executor
Handles tool parsing, execution loop, and tool call management
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Awaitable

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.shared.tool_executor import execute_tool
from backend.app.services.conversation.workflow_tracker import WorkflowTracker

logger = logging.getLogger(__name__)


class PlaybookToolExecutor:
    """Handles tool execution for Playbook runs"""

    def __init__(
        self,
        store: Any,
        workflow_tracker: WorkflowTracker
    ):
        self.store = store
        self.workflow_tracker = workflow_tracker

    async def execute_tool(
        self,
        tool_fqn: str,
        profile_id: str = None,
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        factory_cluster: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Unified tool execution entry point

        This method provides a single entry point for all tool calls from Playbooks.
        It routes to capability package tools via registry, or falls back to legacy services.

        Args:
            tool_fqn: Fully qualified tool name (e.g., "major_proposal.import_template_from_files")
            profile_id: Profile ID (optional, for event recording)
            workspace_id: Workspace ID
            execution_id: Execution ID
            step_id: Step ID
            factory_cluster: Factory cluster name
            **kwargs: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        tool_start_time = datetime.utcnow()
        tool_call_id = str(uuid.uuid4())

        if not factory_cluster:
            if "mcp" in tool_fqn.lower() or tool_fqn.startswith("local_"):
                factory_cluster = "local_mcp"
            elif "sem-" in tool_fqn.lower():
                factory_cluster = "sem-hub"
            elif "wp" in tool_fqn.lower() or "wordpress" in tool_fqn.lower():
                factory_cluster = "wp-hub"
            elif "n8n" in tool_fqn.lower():
                factory_cluster = "n8n"
            else:
                factory_cluster = "local_mcp"

        tool_call = None
        if execution_id:
            try:
                tool_call = self.workflow_tracker.record_tool_call_start(
                    execution_id=execution_id,
                    step_id=step_id or "",
                    tool_name=tool_fqn,
                    parameters=kwargs,
                    factory_cluster=factory_cluster
                )
            except Exception as e:
                logger.warning(f"Failed to create ToolCall record: {e}")

        try:
            normalized_kwargs = kwargs.copy()
            if tool_fqn == "filesystem_write_file" and "path" in normalized_kwargs and "file_path" not in normalized_kwargs:
                normalized_kwargs["file_path"] = normalized_kwargs.pop("path")
                logger.debug(f"Normalized parameter 'path' -> 'file_path' for {tool_fqn}")

            result = await execute_tool(tool_fqn, **normalized_kwargs)

            tool_end_time = datetime.utcnow()
            duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)

            if execution_id and tool_call:
                try:
                    self.workflow_tracker.record_tool_call_complete(
                        tool_call_id=tool_call.id,
                        response={"result": str(result)[:1000]} if result else {"result": result}
                    )
                except Exception as e:
                    logger.warning(f"Failed to update ToolCall record: {e}")

            if profile_id:
                try:
                    project_id = kwargs.get("project_id")
                    event = MindEvent(
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
                            "duration_seconds": (tool_end_time - tool_start_time).total_seconds()
                        },
                        entity_ids=[project_id] if project_id else [],
                        metadata={
                            "tool_params": {k: str(v)[:100] for k, v in kwargs.items() if k != "project_id"},
                            "factory_cluster": factory_cluster
                        }
                    )
                    self.store.create_event(event)
                except Exception as e:
                    logger.warning(f"Failed to record tool call event: {e}")

            return result

        except Exception as e:
            tool_end_time = datetime.utcnow()

            # Update ToolCall record (failed status) using WorkflowTracker
            if execution_id and tool_call:
                try:
                    self.workflow_tracker.record_tool_call_fail(
                        tool_call_id=tool_call.id,
                        error=str(e)[:1000]
                    )
                except Exception as e2:
                    logger.warning(f"Failed to update ToolCall record: {e2}")

            # Record failed tool call event (for backward compatibility)
            if profile_id:
                try:
                    project_id = kwargs.get("project_id")
                    event = MindEvent(
                        id=str(uuid.uuid4()),
                        timestamp=tool_end_time,
                        actor=EventActor.SYSTEM,
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
                            "status": "failed",
                            "error_message": str(e)[:500],
                            "duration_seconds": (tool_end_time - tool_start_time).total_seconds()
                        },
                        entity_ids=[project_id] if project_id else [],
                        metadata={
                            "factory_cluster": factory_cluster
                        }
                    )
                    self.store.create_event(event)
                except Exception as e2:
                    logger.warning(f"Failed to record failed tool call event: {e2}")

            logger.error(f"Failed to execute tool {tool_fqn}: {e}")
            raise

    async def execute_tool_loop(
        self,
        conv_manager: Any,
        assistant_response: str,
        execution_id: str,
        profile_id: str,
        provider: Any,
        model_name: Optional[str] = None,
        max_iterations: int = 5
    ) -> tuple[str, List[str]]:
        """
        Execute tool calls in a loop until no more tools are found or max iterations reached.

        Args:
            conv_manager: ConversationManager instance
            assistant_response: Initial assistant response
            execution_id: Execution ID
            profile_id: Profile ID
            provider: LLM provider instance
            model_name: Model name for LLM calls
            max_iterations: Maximum number of tool execution iterations

        Returns:
            Tuple of (final_assistant_response, used_tools_list)
        """
        max_tool_iterations = max_iterations
        tool_iteration = 0
        used_tools = []
        current_response = assistant_response

        while tool_iteration < max_tool_iterations:
            # Parse tool calls from current assistant response
            tool_calls = conv_manager.parse_tool_calls_from_response(current_response)

            if not tool_calls:
                break  # No tool calls found, exit loop

            logger.info(f"PlaybookToolExecutor: Found {len(tool_calls)} tool call(s) in iteration {tool_iteration + 1}")

            # Execute all tool calls
            tool_results = []
            for tool_call in tool_calls:
                tool_name = tool_call.get("tool_name")
                parameters = tool_call.get("parameters", {})

                if not tool_name:
                    logger.warning(f"Invalid tool call: missing tool_name")
                    continue

                try:
                    # Execute tool
                    logger.info(f"PlaybookToolExecutor: Executing tool {tool_name} with parameters: {list(parameters.keys())}")
                    result = await self.execute_tool(
                        tool_fqn=tool_name,
                        profile_id=profile_id,
                        workspace_id=conv_manager.workspace_id,
                        execution_id=execution_id,
                        step_id=None,  # Will be set when step event is created
                        **parameters
                    )

                    tool_results.append({
                        "tool_name": tool_name,
                        "result": result,
                        "success": True
                    })
                    used_tools.append(tool_name)

                    logger.info(f"PlaybookToolExecutor: Tool {tool_name} executed successfully")

                except Exception as e:
                    error_msg = str(e)[:500]
                    logger.error(f"PlaybookToolExecutor: Tool {tool_name} execution failed: {e}", exc_info=True)
                    tool_results.append({
                        "tool_name": tool_name,
                        "result": None,
                        "success": False,
                        "error": error_msg
                    })

            # Add tool call results to conversation
            if tool_results:
                conv_manager.add_tool_call_results(tool_results)

            # Continue conversation with tool results
            # Only continue if we have successful tool calls (to avoid infinite loops on errors)
            if any(r.get("success", False) for r in tool_results):
                messages = conv_manager.get_messages_for_llm()
                current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                conv_manager.add_assistant_message(current_response)
                tool_iteration += 1
            else:
                # All tool calls failed, exit loop
                logger.warning(f"PlaybookToolExecutor: All tool calls failed, exiting tool execution loop")
                break

        return current_response, used_tools

