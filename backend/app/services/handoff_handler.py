"""
Handoff Handler - Coordinate cross-engine task execution

The Handoff Handler orchestrates seamless transitions between different execution
engines (Playbook, Claude Skills, MCP, n8n) by managing the handoff events and
coordinating state transfer through Task IR.

This is the "conductor" in our video editing analogy - it knows when to pass
work from one tool to another and ensures smooth transitions.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, List, Optional

from backend.app.models.task_ir import (
    TaskIR, TaskIRUpdate, HandoffEvent, ExecutionEngine,
    TaskStatus, PhaseStatus, ExecutionMetadata
)
from backend.app.services.stores.task_ir_store import TaskIRStore
from backend.app.services.artifact_registry import ArtifactRegistry
from backend.app.services.playbook_ir_adapter import PlaybookIRAdapter
from backend.app.services.skill_ir_adapter import SkillIRAdapter

logger = logging.getLogger(__name__)


class HandoffHandler:
    """
    Handles handoffs between different execution engines

    This service coordinates the transfer of execution context between
    different engines, ensuring that each engine gets the right inputs
    and that results are properly captured and forwarded.
    """

    def __init__(
        self,
        task_ir_store: TaskIRStore,
        artifact_registry: ArtifactRegistry,
        playbook_adapter: Optional[PlaybookIRAdapter] = None,
        skill_adapter: Optional[SkillIRAdapter] = None
    ):
        """
        Initialize handoff handler

        Args:
            task_ir_store: Store for Task IR persistence
            artifact_registry: Registry for artifact management
            playbook_adapter: Optional playbook adapter
            skill_adapter: Optional skill adapter
        """
        self.task_ir_store = task_ir_store
        self.artifact_registry = artifact_registry
        self.playbook_adapter = playbook_adapter
        self.skill_adapter = skill_adapter

        # Initialize adapters if not provided
        if not self.playbook_adapter:
            self.playbook_adapter = PlaybookIRAdapter(artifact_registry)
        if not self.skill_adapter:
            self.skill_adapter = SkillIRAdapter(artifact_registry)

    async def handle_handoff(self, handoff_event: HandoffEvent) -> Dict[str, Any]:
        """
        Process a handoff event

        This method coordinates the transfer of execution from one engine
        to another, updating Task IR and preparing the next engine's inputs.

        Args:
            handoff_event: Handoff event to process

        Returns:
            Handoff result with execution details
        """
        logger.info(f"Processing handoff: {handoff_event.event_type} from {handoff_event.from_engine} "
                   f"to {handoff_event.to_engine}")

        # Load current Task IR
        task_ir = self.task_ir_store.get_task_ir(handoff_event.task_ir.task_id)
        if not task_ir:
            raise ValueError(f"Task IR {handoff_event.task_ir.task_id} not found")

        # Route to appropriate handler based on target engine
        target_engine_type = handoff_event.to_engine.split(':')[0]

        if target_engine_type == ExecutionEngine.PLAYBOOK.value:
            return await self._handoff_to_playbook(handoff_event, task_ir)
        elif target_engine_type == ExecutionEngine.SKILL.value:
            return await self._handoff_to_skill(handoff_event, task_ir)
        elif target_engine_type == ExecutionEngine.MCP.value:
            return await self._handoff_to_mcp(handoff_event, task_ir)
        elif target_engine_type == ExecutionEngine.N8N.value:
            return await self._handoff_to_n8n(handoff_event, task_ir)
        else:
            raise ValueError(f"Unsupported target engine: {handoff_event.to_engine}")

    async def initiate_task_execution(
        self,
        task_ir: TaskIR,
        starting_engine: str
    ) -> Dict[str, Any]:
        """
        Initiate execution of a new task

        Args:
            task_ir: Task IR to execute
            starting_engine: Engine to start with

        Returns:
            Execution initiation result
        """
        # Save initial Task IR
        self.task_ir_store.create_task_ir(task_ir)

        # Find first executable phase
        executable_phases = task_ir.get_next_executable_phases()
        if not executable_phases:
            return {
                "success": False,
                "error": "No executable phases found"
            }

        first_phase = executable_phases[0]

        # Create handoff event to starting engine
        handoff_event = HandoffEvent(
            event_type=f"handoff.to_{starting_engine.split(':')[0]}",
            timestamp=_utc_now(),
            from_engine="system",
            from_execution_id="",
            from_phase_id="",
            to_engine=starting_engine,
            to_execution_id=None,
            task_ir=task_ir,
            input_artifacts=[],
            input_summary="Task initialization",
            workspace_id=task_ir.workspace_id,
            metadata=task_ir.metadata
        )

        # Execute the handoff
        result = await self.handle_handoff(handoff_event)

        logger.info(f"Initiated task {task_ir.task_id} execution with engine {starting_engine}")
        return result

    async def _handoff_to_playbook(
        self,
        handoff_event: HandoffEvent,
        task_ir: TaskIR
    ) -> Dict[str, Any]:
        """Handle handoff to playbook engine"""
        try:
            # Extract target playbook
            playbook_code = handoff_event.to_engine.replace("playbook:", "")

            # Prepare playbook inputs from Task IR
            current_phase = handoff_event.task_ir.current_phase
            if not current_phase:
                raise ValueError("No current phase specified for playbook handoff")

            playbook_inputs = await self.playbook_adapter.task_ir_to_playbook_inputs(
                task_ir, current_phase
            )

            # Import playbook service
            from backend.app.services.playbook_service import PlaybookService
            playbook_service = PlaybookService()

            # Execute playbook
            execution_result = await playbook_service.execute_playbook(
                playbook_code=playbook_code,
                profile_id="system",  # Use system profile for handoffs
                inputs=playbook_inputs,
                workspace_id=task_ir.workspace_id,
                target_language="zh-TW"
            )

            # Convert playbook output back to Task IR updates
            ir_update = await self.playbook_adapter.playbook_output_to_task_ir(
                execution_result.result or {},
                execution_result.execution_id,
                current_phase,
                task_ir
            )

            # Update Task IR
            success = self.task_ir_store.update_task_ir(task_ir.task_id, ir_update)

            # Determine next phase
            next_phase = self._determine_next_phase(task_ir, ir_update)

            return {
                "success": success,
                "execution_id": execution_result.execution_id,
                "target_engine": handoff_event.to_engine,
                "phase_completed": current_phase,
                "next_phase": next_phase,
                "artifacts_created": len(ir_update.new_artifacts)
            }

        except Exception as e:
            logger.error(f"Playbook handoff failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "target_engine": handoff_event.to_engine
            }

    async def _handoff_to_skill(
        self,
        handoff_event: HandoffEvent,
        task_ir: TaskIR
    ) -> Dict[str, Any]:
        """Handle handoff to Claude Skill engine"""
        try:
            # Extract target skill
            skill_id = handoff_event.to_engine.replace("skill:", "")

            # Prepare skill context from Task IR
            current_phase = handoff_event.task_ir.current_phase
            if not current_phase:
                raise ValueError("No current phase specified for skill handoff")

            skill_context = await self.skill_adapter.task_ir_to_skill_context(
                task_ir, current_phase
            )

            # Import semantic hub client (placeholder for actual implementation)
            # from backend.app.services.clients.semantic_hub_client import SemanticHubClient
            # semantic_hub = SemanticHubClient(base_url=settings.SEMANTIC_HUB_URL)

            # For now, simulate skill execution
            skill_result = await self._simulate_skill_execution(skill_id, skill_context)

            # Convert skill output back to Task IR updates
            ir_update = await self.skill_adapter.skill_output_to_task_ir(
                skill_result,
                f"skill_exec_{skill_id}_{int(_utc_now().timestamp())}",
                current_phase,
                task_ir
            )

            # Update Task IR
            success = self.task_ir_store.update_task_ir(task_ir.task_id, ir_update)

            # Determine next phase
            next_phase = self._determine_next_phase(task_ir, ir_update)

            return {
                "success": success,
                "execution_id": f"skill_{skill_id}",
                "target_engine": handoff_event.to_engine,
                "phase_completed": current_phase,
                "next_phase": next_phase,
                "artifacts_created": len(ir_update.new_artifacts)
            }

        except Exception as e:
            logger.error(f"Skill handoff failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "target_engine": handoff_event.to_engine
            }

    async def _handoff_to_mcp(
        self,
        handoff_event: HandoffEvent,
        task_ir: TaskIR
    ) -> Dict[str, Any]:
        """Handle handoff to MCP engine"""
        # Placeholder for MCP integration
        logger.info(f"MCP handoff requested but not yet implemented: {handoff_event.to_engine}")
        return {
            "success": False,
            "error": "MCP handoff not yet implemented",
            "target_engine": handoff_event.to_engine
        }

    async def _handoff_to_n8n(
        self,
        handoff_event: HandoffEvent,
        task_ir: TaskIR
    ) -> Dict[str, Any]:
        """Handle handoff to n8n engine"""
        # Placeholder for n8n integration
        logger.info(f"n8n handoff requested but not yet implemented: {handoff_event.to_engine}")
        return {
            "success": False,
            "error": "n8n handoff not yet implemented",
            "target_engine": handoff_event.to_engine
        }

    def _determine_next_phase(self, task_ir: TaskIR, recent_update: TaskIRUpdate) -> Optional[str]:
        """
        Determine the next phase to execute after a handoff

        Args:
            task_ir: Current Task IR
            recent_update: Recent update that may have completed phases

        Returns:
            Next phase ID or None if no more phases
        """
        # Reload Task IR to get updated state
        updated_task_ir = self.task_ir_store.get_task_ir(task_ir.task_id)
        if not updated_task_ir:
            return None

        # Find next executable phase
        executable_phases = updated_task_ir.get_next_executable_phases()
        if executable_phases:
            return executable_phases[0].id

        return None

    async def _simulate_skill_execution(self, skill_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate Claude Skill execution (placeholder)

        In a real implementation, this would call the actual Semantic Hub API.

        Args:
            skill_id: Skill identifier
            context: Skill context

        Returns:
            Simulated skill result
        """
        # This is a placeholder implementation
        # In production, this would make an actual API call to Claude Skills

        await asyncio.sleep(1)  # Simulate processing time

        return {
            "summary": f"Skill {skill_id} executed successfully on task {context['task_id']}, phase {context['phase_id']}.",
            "artifacts": [
                {
                    "name": "analysis_result.json",
                    "content": {"status": "completed", "skill_id": skill_id},
                    "type": "application/json"
                }
            ],
            "result": {"completed": True, "skill_id": skill_id}
        }

    async def create_handoff_event(
        self,
        from_engine: str,
        to_engine: str,
        task_ir: TaskIR,
        phase_id: str,
        input_artifacts: Optional[List[str]] = None,
        input_summary: Optional[str] = None
    ) -> HandoffEvent:
        """
        Create a handoff event

        Args:
            from_engine: Source engine
            to_engine: Target engine
            task_ir: Task IR
            phase_id: Current phase
            input_artifacts: Artifacts to pass
            input_summary: Summary for handoff

        Returns:
            Handoff event
        """
        return HandoffEvent(
            event_type=f"handoff.to_{to_engine.split(':')[0]}",
            timestamp=_utc_now(),
            from_engine=from_engine,
            from_execution_id="",  # Would be filled by caller
            from_phase_id=phase_id,
            to_engine=to_engine,
            to_execution_id=None,
            task_ir=task_ir,
            input_artifacts=input_artifacts or [],
            input_summary=input_summary or "",
            workspace_id=task_ir.workspace_id,
            metadata=task_ir.metadata
        )

    async def get_handoff_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get current handoff status for a task

        Args:
            task_id: Task ID

        Returns:
            Status information
        """
        task_ir = self.task_ir_store.get_task_ir(task_id)
        if not task_ir:
            return {"status": "not_found"}

        current_phase = task_ir.get_phase(task_ir.current_phase) if task_ir.current_phase else None

        return {
            "task_id": task_id,
            "status": task_ir.status,
            "current_phase": {
                "id": current_phase.id if current_phase else None,
                "name": current_phase.name if current_phase else None,
                "status": current_phase.status if current_phase else None,
                "preferred_engine": current_phase.preferred_engine if current_phase else None
            } if current_phase else None,
            "completed_phases": len(task_ir.get_completed_phases()),
            "total_phases": len(task_ir.phases),
            "last_checkpoint": task_ir.last_checkpoint_at.isoformat() if task_ir.last_checkpoint_at else None
        }

    async def cancel_handoff(self, task_id: str, reason: str = "User cancelled") -> bool:
        """
        Cancel a handoff in progress

        Args:
            task_id: Task ID
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        task_ir = self.task_ir_store.get_task_ir(task_id)
        if not task_ir:
            return False

        # Update task status to failed
        update = TaskIRUpdate(status_update=TaskStatus.FAILED.value)
        success = self.task_ir_store.update_task_ir(task_id, update)

        if success:
            logger.info(f"Cancelled handoff for task {task_id}: {reason}")

        return success


# Import asyncio for the simulation
import asyncio
