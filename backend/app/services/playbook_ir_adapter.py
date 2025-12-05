"""
Playbook IR Adapter - Convert between Task IR and Playbook formats

This adapter enables seamless handoffs between playbook executions and other
execution engines by translating between Task IR (the universal format) and
playbook-specific data structures.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from backend.app.models.task_ir import (
    TaskIR, TaskIRUpdate, PhaseIR, ArtifactReference,
    ExecutionEngine, TaskStatus, PhaseStatus, ExecutionMetadata
)
from backend.app.services.artifact_registry import ArtifactRegistry
from backend.app.models.playbook import PlaybookRun

logger = logging.getLogger(__name__)


class PlaybookIRAdapter:
    """
    Adapter for converting between Task IR and Playbook execution formats

    This adapter handles the "language translation" between the universal
    Task IR format and playbook-specific execution contexts, inputs, and outputs.
    """

    def __init__(self, artifact_registry: ArtifactRegistry):
        """
        Initialize adapter

        Args:
            artifact_registry: Artifact registry for content management
        """
        self.artifact_registry = artifact_registry

    async def task_ir_to_playbook_inputs(
        self,
        task_ir: TaskIR,
        phase_id: str
    ) -> Dict[str, Any]:
        """
        Convert Task IR context to Playbook input format

        This prepares the inputs that a playbook expects based on the
        current Task IR state, including artifacts from previous phases.

        Args:
            task_ir: Current Task IR
            phase_id: Phase being executed

        Returns:
            Playbook input dictionary
        """
        phase = task_ir.get_phase(phase_id)
        if not phase:
            raise ValueError(f"Phase {phase_id} not found in Task IR {task_ir.task_id}")

        inputs = {
            "task_context": {
                "task_id": task_ir.task_id,
                "intent_instance_id": task_ir.intent_instance_id,
                "current_phase": phase_id,
                "workspace_id": task_ir.workspace_id
            },
            "artifacts": {},
            "phase_summaries": []
        }

        # Load artifacts from dependent phases
        if phase.depends_on:
            for dep_phase_id in phase.depends_on:
                dep_phase = task_ir.get_phase(dep_phase_id)
                if dep_phase and dep_phase.output_artifacts:
                    for artifact_id in dep_phase.output_artifacts:
                        artifact = task_ir.get_artifact(artifact_id)
                        if artifact:
                            try:
                                content = await self.artifact_registry.load_artifact_content(artifact_id)
                                inputs["artifacts"][artifact_id] = {
                                    "content": content,
                                    "type": artifact.type,
                                    "source": artifact.source,
                                    "metadata": artifact.metadata
                                }
                            except Exception as e:
                                logger.warning(f"Failed to load artifact {artifact_id}: {e}")

        # Collect phase summaries for context
        completed_phases = task_ir.get_completed_phases()
        for completed_phase in completed_phases:
            if completed_phase.summary_artifact:
                try:
                    summary_content = await self.artifact_registry.load_artifact_content(
                        completed_phase.summary_artifact
                    )
                    inputs["phase_summaries"].append({
                        "phase_id": completed_phase.id,
                        "name": completed_phase.name,
                        "summary": summary_content,
                        "completed_at": completed_phase.completed_at.isoformat() if completed_phase.completed_at else None
                    })
                except Exception as e:
                    logger.warning(f"Failed to load phase summary for {completed_phase.id}: {e}")

        # Add intent context if available
        if task_ir.metadata.intent:
            inputs["intent_context"] = task_ir.metadata.intent

        logger.info(f"Converted Task IR {task_ir.task_id} phase {phase_id} to playbook inputs")
        return inputs

    async def playbook_output_to_task_ir(
        self,
        playbook_output: Dict[str, Any],
        execution_id: str,
        phase_id: str,
        task_ir: TaskIR
    ) -> TaskIRUpdate:
        """
        Convert Playbook execution output to Task IR updates

        This takes the outputs from a playbook execution and converts them
        into Task IR updates, including new artifacts and phase status changes.

        Args:
            playbook_output: Playbook execution results
            execution_id: Playbook execution ID
            phase_id: Phase that was executed
            task_ir: Current Task IR

        Returns:
            Task IR update operations
        """
        update = TaskIRUpdate()
        new_artifacts = []

        # Process outputs and create artifacts
        for output_key, output_value in playbook_output.items():
            if output_key.startswith('_'):  # Skip internal keys
                continue

            # Determine artifact type
            artifact_type = self._infer_artifact_type(output_value)

            # Create artifact ID
            artifact_id = f"{task_ir.task_id}/{phase_id}/{output_key}"

            # Create artifact reference
            artifact = ArtifactReference(
                id=artifact_id,
                type=artifact_type,
                source=f"playbook:{execution_id}",
                uri="",  # Will be set by registry
                metadata={
                    "phase_id": phase_id,
                    "output_key": output_key,
                    "execution_id": execution_id
                }
            )

            # Register artifact
            await self.artifact_registry.register_artifact(artifact, output_value)
            new_artifacts.append(artifact)

        # Update phase status
        phase_updates = {
            phase_id: {
                "status": PhaseStatus.COMPLETED.value,
                "executed_by": f"playbook:{execution_id}",
                "execution_id": execution_id,
                "output_artifacts": [a.id for a in new_artifacts],
                "completed_at": datetime.utcnow().isoformat()
            }
        }

        # Create summary artifact if playbook provided one
        if "summary" in playbook_output:
            summary_artifact_id = f"{task_ir.task_id}/{phase_id}/summary"
            summary_artifact = ArtifactReference(
                id=summary_artifact_id,
                type="text/markdown",
                source=f"playbook:{execution_id}",
                uri="",
                metadata={
                    "phase_id": phase_id,
                    "execution_id": execution_id,
                    "type": "phase_summary"
                }
            )

            await self.artifact_registry.register_artifact(
                summary_artifact,
                playbook_output["summary"]
            )
            new_artifacts.append(summary_artifact)
            phase_updates[phase_id]["summary_artifact"] = summary_artifact_id

        update.phase_updates = phase_updates
        update.new_artifacts = new_artifacts

        logger.info(f"Converted playbook output from execution {execution_id} to Task IR updates: "
                   f"{len(phase_updates)} phase updates, {len(new_artifacts)} artifacts")

        return update

    async def create_task_ir_from_playbook_run(
        self,
        playbook_run: PlaybookRun,
        workspace_id: str,
        actor_id: str,
        intent_instance_id: Optional[str] = None
    ) -> TaskIR:
        """
        Create Task IR from a PlaybookRun

        This initializes a Task IR when starting a playbook execution,
        setting up the phase structure based on the playbook definition.

        Args:
            playbook_run: Playbook run configuration
            workspace_id: Workspace ID
            actor_id: Actor initiating the task
            intent_instance_id: Optional intent instance ID

        Returns:
            Initialized Task IR
        """
        import uuid

        task_id = f"task_{uuid.uuid4().hex[:16]}"

        # Create execution metadata
        metadata = ExecutionMetadata()
        metadata.set_execution_context(
            playbook_code=playbook_run.playbook.metadata.playbook_code
        )
        if intent_instance_id:
            metadata.set_intent_context(intent_instance_id=intent_instance_id)

        # Create phases from playbook JSON if available
        phases = []
        if playbook_run.playbook_json and playbook_run.playbook_json.steps:
            for i, step in enumerate(playbook_run.playbook_json.steps):
                phase = PhaseIR(
                    id=f"step_{i}",
                    name=step.get("name", f"Step {i+1}"),
                    description=step.get("description", ""),
                    status=PhaseStatus.PENDING.value,
                    preferred_engine=f"playbook:{playbook_run.playbook.metadata.playbook_code}",
                    depends_on=[f"step_{j}" for j in range(i) if step.get("depends_on")]  # Simplified
                )
                phases.append(phase)
        else:
            # Single phase for simple playbooks
            phase = PhaseIR(
                id="main",
                name="Main Execution",
                description=f"Execute {playbook_run.playbook.metadata.name}",
                status=PhaseStatus.PENDING.value,
                preferred_engine=f"playbook:{playbook_run.playbook.metadata.playbook_code}"
            )
            phases.append(phase)

        # Create Task IR
        task_ir = TaskIR(
            task_id=task_id,
            intent_instance_id=intent_instance_id or task_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            current_phase=phases[0].id if phases else None,
            status=TaskStatus.PENDING.value,
            phases=phases,
            artifacts=[],
            metadata=metadata
        )

        logger.info(f"Created Task IR {task_id} from playbook {playbook_run.playbook.metadata.playbook_code}")
        return task_ir

    async def can_playbook_handle_phase(self, task_ir: TaskIR, phase_id: str) -> bool:
        """
        Check if a playbook engine can handle a specific phase

        Args:
            task_ir: Task IR
            phase_id: Phase to check

        Returns:
            True if playbook can handle this phase
        """
        phase = task_ir.get_phase(phase_id)
        if not phase or not phase.preferred_engine:
            return False

        return phase.preferred_engine.startswith("playbook:")

    def _infer_artifact_type(self, content: Any) -> str:
        """
        Infer MIME type from content

        Args:
            content: Content to analyze

        Returns:
            MIME type string
        """
        if isinstance(content, dict):
            return "application/json"
        elif isinstance(content, list):
            return "application/json"
        elif isinstance(content, str):
            # Check if it looks like markdown
            if any(marker in content for marker in ['# ', '## ', '- ', '* ', '```']):
                return "text/markdown"
            else:
                return "text/plain"
        elif isinstance(content, (int, float)):
            return "application/json"  # Will be wrapped
        else:
            return "application/octet-stream"

    async def get_playbook_context_summary(self, task_ir: TaskIR) -> str:
        """
        Generate a playbook-friendly context summary from Task IR

        Args:
            task_ir: Task IR to summarize

        Returns:
            Context summary string
        """
        summary_parts = [
            f"Task: {task_ir.task_id}",
            f"Intent: {task_ir.intent_instance_id}",
            f"Current Phase: {task_ir.current_phase or 'None'}",
            f"Status: {task_ir.status}",
            ""
        ]

        # Add completed phases summary
        completed_phases = task_ir.get_completed_phases()
        if completed_phases:
            summary_parts.append("Completed Phases:")
            for phase in completed_phases:
                summary_parts.append(f"- {phase.name} ({phase.id})")
                if phase.summary_artifact:
                    try:
                        summary_content = await self.artifact_registry.load_artifact_content(
                            phase.summary_artifact
                        )
                        # Truncate long summaries
                        if len(summary_content) > 200:
                            summary_content = summary_content[:200] + "..."
                        summary_parts.append(f"  Summary: {summary_content}")
                    except Exception as e:
                        logger.debug(f"Could not load summary for phase {phase.id}: {e}")
            summary_parts.append("")

        # Add available artifacts
        if task_ir.artifacts:
            summary_parts.append("Available Artifacts:")
            for artifact in task_ir.artifacts[-5:]:  # Last 5 artifacts
                summary_parts.append(f"- {artifact.id} ({artifact.type}) from {artifact.source}")
            if len(task_ir.artifacts) > 5:
                summary_parts.append(f"... and {len(task_ir.artifacts) - 5} more")
            summary_parts.append("")

        return "\n".join(summary_parts)
