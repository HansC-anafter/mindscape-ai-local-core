"""
Skill IR Adapter - Convert between Task IR and Claude Skill formats

This adapter enables seamless handoffs between Claude Skill executions and other
execution engines by translating between Task IR (the universal format) and
skill-specific prompt contexts and result formats.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from backend.app.models.task_ir import (
    TaskIR, TaskIRUpdate, PhaseIR, ArtifactReference,
    ExecutionEngine, TaskStatus, PhaseStatus, ExecutionMetadata
)
from backend.app.services.artifact_registry import ArtifactRegistry

logger = logging.getLogger(__name__)


class SkillIRAdapter:
    """
    Adapter for converting between Task IR and Claude Skill formats

    This adapter handles the translation between universal Task IR and
    Claude Skill's expected input/output formats, including prompt context
    construction and result parsing.
    """

    def __init__(self, artifact_registry: ArtifactRegistry):
        """
        Initialize adapter

        Args:
            artifact_registry: Artifact registry for content management
        """
        self.artifact_registry = artifact_registry

    async def task_ir_to_skill_context(
        self,
        task_ir: TaskIR,
        phase_id: str
    ) -> Dict[str, Any]:
        """
        Convert Task IR context to Claude Skill input format

        This prepares the context that a Claude Skill expects, including
        relevant artifacts, phase summaries, and task background.

        Args:
            task_ir: Current Task IR
            phase_id: Phase being executed

        Returns:
            Skill context dictionary
        """
        phase = task_ir.get_phase(phase_id)
        if not phase:
            raise ValueError(f"Phase {phase_id} not found in Task IR {task_ir.task_id}")

        context = {
            "task_id": task_ir.task_id,
            "intent_instance_id": task_ir.intent_instance_id,
            "workspace_id": task_ir.workspace_id,
            "phase_id": phase_id,
            "phase_name": phase.name,
            "phase_description": phase.description,
            "files": [],
            "context_summary": "",
            "previous_phases": [],
            "available_artifacts": []
        }

        # Load input artifacts as files
        if phase.depends_on:
            for dep_phase_id in phase.depends_on:
                dep_phase = task_ir.get_phase(dep_phase_id)
                if dep_phase and dep_phase.output_artifacts:
                    for artifact_id in dep_phase.output_artifacts:
                        artifact = task_ir.get_artifact(artifact_id)
                        if artifact:
                            try:
                                content = await self.artifact_registry.load_artifact_content(artifact_id)
                                context["files"].append({
                                    "name": f"{artifact_id.split('/')[-1]}",
                                    "path": artifact.uri,
                                    "content": content,
                                    "type": artifact.type,
                                    "source": artifact.source
                                })
                            except Exception as e:
                                logger.warning(f"Failed to load artifact {artifact_id} for skill context: {e}")

        # Build context summary
        context_parts = [
            f"Task: {task_ir.task_id}",
            f"Intent: {task_ir.intent_instance_id}",
            f"Current Phase: {phase.name}",
            ""
        ]

        # Add completed phases information
        completed_phases = task_ir.get_completed_phases()
        for completed_phase in completed_phases:
            context_parts.append(f"Completed: {completed_phase.name}")
            if completed_phase.summary_artifact:
                try:
                    summary = await self.artifact_registry.load_artifact_content(
                        completed_phase.summary_artifact
                    )
                    context_parts.append(f"Summary: {summary[:200]}{'...' if len(summary) > 200 else ''}")
                except Exception as e:
                    logger.debug(f"Could not load summary for phase {completed_phase.id}: {e}")
            context_parts.append("")

        context["context_summary"] = "\n".join(context_parts)

        # Add previous phases summary
        context["previous_phases"] = [
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None
            }
            for p in completed_phases
        ]

        # Add available artifacts summary
        context["available_artifacts"] = [
            {
                "id": a.id,
                "type": a.type,
                "source": a.source,
                "created_at": a.created_at.isoformat()
            }
            for a in task_ir.artifacts
        ]

        # Add intent context if available
        if task_ir.metadata.intent:
            context["intent_context"] = task_ir.metadata.intent

        logger.info(f"Converted Task IR {task_ir.task_id} phase {phase_id} to skill context "
                   f"with {len(context['files'])} files")

        return context

    async def skill_output_to_task_ir(
        self,
        skill_output: Dict[str, Any],
        skill_execution_id: str,
        phase_id: str,
        task_ir: TaskIR
    ) -> TaskIRUpdate:
        """
        Convert Claude Skill output to Task IR updates

        This parses the results from a Claude Skill execution and converts
        them into Task IR updates, creating appropriate artifacts and updating
        phase status.

        Args:
            skill_output: Skill execution results
            skill_execution_id: Skill execution ID
            phase_id: Phase that was executed
            task_ir: Current Task IR

        Returns:
            Task IR update operations
        """
        update = TaskIRUpdate()
        new_artifacts = []

        # Claude Skill output typically includes:
        # - summary: str (phase summary)
        # - artifacts: List[Dict] (additional outputs)
        # - result: Any (main result)

        # Create summary artifact
        if "summary" in skill_output:
            summary_artifact_id = f"{task_ir.task_id}/{phase_id}/summary"
            summary_artifact = ArtifactReference(
                id=summary_artifact_id,
                type="text/markdown",
                source=f"skill:{skill_execution_id}",
                uri="",
                metadata={
                    "phase_id": phase_id,
                    "execution_id": skill_execution_id,
                    "type": "phase_summary"
                }
            )

            await self.artifact_registry.register_artifact(
                summary_artifact,
                skill_output["summary"]
            )
            new_artifacts.append(summary_artifact)

        # Process additional artifacts from skill output
        if "artifacts" in skill_output:
            for i, artifact_data in enumerate(skill_output["artifacts"]):
                artifact_id = f"{task_ir.task_id}/{phase_id}/artifact_{i}"
                artifact_type = artifact_data.get("type", "text/plain")

                artifact = ArtifactReference(
                    id=artifact_id,
                    type=artifact_type,
                    source=f"skill:{skill_execution_id}",
                    uri="",
                    metadata={
                        "phase_id": phase_id,
                        "execution_id": skill_execution_id,
                        "name": artifact_data.get("name", f"artifact_{i}")
                    }
                )

                content = artifact_data.get("content", "")
                await self.artifact_registry.register_artifact(artifact, content)
                new_artifacts.append(artifact)

        # Process main result if present
        if "result" in skill_output:
            result_artifact_id = f"{task_ir.task_id}/{phase_id}/result"
            result_artifact = ArtifactReference(
                id=result_artifact_id,
                type=self._infer_result_type(skill_output["result"]),
                source=f"skill:{skill_execution_id}",
                uri="",
                metadata={
                    "phase_id": phase_id,
                    "execution_id": skill_execution_id,
                    "type": "main_result"
                }
            )

            await self.artifact_registry.register_artifact(
                result_artifact,
                skill_output["result"]
            )
            new_artifacts.append(artifact)

        # Update phase status
        phase_updates = {
            phase_id: {
                "status": PhaseStatus.COMPLETED.value,
                "executed_by": f"skill:{skill_execution_id}",
                "execution_id": skill_execution_id,
                "output_artifacts": [a.id for a in new_artifacts],
                "completed_at": datetime.utcnow().isoformat()
            }
        }

        # Set summary artifact if created
        summary_artifacts = [a for a in new_artifacts if a.metadata.get("type") == "phase_summary"]
        if summary_artifacts:
            phase_updates[phase_id]["summary_artifact"] = summary_artifacts[0].id

        update.phase_updates = phase_updates
        update.new_artifacts = new_artifacts

        logger.info(f"Converted skill output from execution {skill_execution_id} to Task IR updates: "
                   f"{len(phase_updates)} phase updates, {len(new_artifacts)} artifacts")

        return update

    async def can_skill_handle_phase(self, task_ir: TaskIR, phase_id: str, skill_id: str) -> bool:
        """
        Check if a specific Claude Skill can handle a phase

        Args:
            task_ir: Task IR
            phase_id: Phase to check
            skill_id: Skill identifier

        Returns:
            True if skill can handle this phase
        """
        phase = task_ir.get_phase(phase_id)
        if not phase or not phase.preferred_engine:
            return False

        return phase.preferred_engine == f"skill:{skill_id}"

    def _infer_result_type(self, result: Any) -> str:
        """
        Infer MIME type for skill result

        Args:
            result: Result to analyze

        Returns:
            MIME type string
        """
        if isinstance(result, dict):
            return "application/json"
        elif isinstance(result, list):
            return "application/json"
        elif isinstance(result, str):
            if len(result) > 1000:  # Long text might be markdown
                return "text/markdown"
            else:
                return "text/plain"
        elif isinstance(result, (int, float, bool)):
            return "application/json"
        else:
            return "text/plain"

    async def create_skill_prompt_context(self, task_ir: TaskIR, phase_id: str) -> str:
        """
        Create a rich prompt context for Claude Skill execution

        Args:
            task_ir: Task IR
            phase_id: Current phase

        Returns:
            Formatted prompt context
        """
        phase = task_ir.get_phase(phase_id)
        if not phase:
            return "No phase information available."

        prompt_parts = [
            f"# Task Context",
            f"",
            f"**Task ID:** {task_ir.task_id}",
            f"**Intent:** {task_ir.intent_instance_id}",
            f"**Current Phase:** {phase.name}",
            f"**Phase Description:** {phase.description or 'No description available'}",
            f"",
            f"## Task History",
            f""
        ]

        # Add completed phases
        completed_phases = task_ir.get_completed_phases()
        if completed_phases:
            for completed_phase in completed_phases:
                prompt_parts.append(f"### ✅ {completed_phase.name}")
                if completed_phase.summary_artifact:
                    try:
                        summary = await self.artifact_registry.load_artifact_content(
                            completed_phase.summary_artifact
                        )
                        prompt_parts.append(f"**Summary:** {summary}")
                    except Exception as e:
                        logger.debug(f"Could not load summary: {e}")
                prompt_parts.append("")
        else:
            prompt_parts.append("*No previous phases completed*")
            prompt_parts.append("")

        # Add available resources
        if task_ir.artifacts:
            prompt_parts.append("## Available Resources")
            prompt_parts.append("")
            for artifact in task_ir.artifacts:
                prompt_parts.append(f"- **{artifact.id}** ({artifact.type}) from {artifact.source}")
            prompt_parts.append("")

        # Add phase-specific instructions
        prompt_parts.append("## Current Phase Requirements")
        prompt_parts.append("")
        prompt_parts.append(f"Please execute the phase: **{phase.name}**")
        if phase.description:
            prompt_parts.append(f"Description: {phase.description}")
        prompt_parts.append("")
        prompt_parts.append("Provide your results in the expected format with summary and any artifacts.")

        return "\n".join(prompt_parts)

    async def parse_skill_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and normalize Claude Skill response

        Args:
            response: Raw skill response

        Returns:
            Normalized response format
        """
        normalized = {
            "summary": "",
            "artifacts": [],
            "result": None
        }

        # Extract summary
        if "summary" in response:
            normalized["summary"] = str(response["summary"])
        elif "description" in response:
            normalized["summary"] = str(response["description"])
        elif "output" in response and isinstance(response["output"], str):
            normalized["summary"] = response["output"]

        # Extract artifacts
        if "artifacts" in response and isinstance(response["artifacts"], list):
            normalized["artifacts"] = response["artifacts"]
        elif "files" in response and isinstance(response["files"], list):
            normalized["artifacts"] = response["files"]
        elif "outputs" in response and isinstance(response["outputs"], list):
            normalized["artifacts"] = response["outputs"]

        # Extract main result
        if "result" in response:
            normalized["result"] = response["result"]
        elif "data" in response:
            normalized["result"] = response["data"]
        elif "value" in response:
            normalized["result"] = response["value"]

        return normalized
