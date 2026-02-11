"""
Project Memory Service

Manages project-specific memory including:
- Decision history and rationale
- Version evolution and changes
- Artifact index and dependencies
- Key conversation summaries
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class DecisionRecord(BaseModel):
    """Record of a decision made during project execution"""

    id: str = Field(..., description="Decision record ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Decision timestamp")
    decision: str = Field(..., description="Decision made")
    rationale: str = Field(..., description="Reasoning behind the decision")
    alternatives_considered: Optional[List[str]] = Field(None, description="Alternatives considered")
    decision_maker: Optional[str] = Field(None, description="Who made the decision")


class VersionEvolution(BaseModel):
    """Version evolution record"""

    version: str = Field(..., description="Version identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Version timestamp")
    summary: str = Field(..., description="Version summary")
    key_changes: List[str] = Field(default_factory=list, description="Key changes in this version")
    artifacts: Optional[List[str]] = Field(None, description="Artifacts in this version")


class ProjectMemory(BaseModel):
    """
    Project Memory - project-specific context and history

    Stores project-specific information that evolves over time:
    - Decision history and rationale
    - Version evolution
    - Artifact index
    - Key conversation summaries
    """

    project_id: str = Field(..., description="Project ID")
    decision_history: List[DecisionRecord] = Field(
        default_factory=list,
        description="History of decisions made during project"
    )
    version_evolution: List[VersionEvolution] = Field(
        default_factory=list,
        description="Version evolution history"
    )
    artifact_index: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Index of artifacts created in this project"
    )
    key_conversations: List[str] = Field(
        default_factory=list,
        description="Summaries of key conversations"
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProjectMemoryService:
    """
    Service for managing project memory

    Provides methods to read and update project-specific memory,
    which persists throughout the project lifecycle.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize Project Memory Service

        Args:
            store: MindscapeStore instance
        """
        self.store = store
        self.project_manager = ProjectManager(store)

    async def get_project_memory(
        self,
        project_id: str,
        workspace_id: str
    ) -> ProjectMemory:
        """
        Get project memory

        Loads memory from project metadata, or creates default if not exists.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID (for validation)

        Returns:
            ProjectMemory instance
        """
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        memory_data = project.metadata.get("project_memory", {})

        if not memory_data:
            return ProjectMemory(
                project_id=project_id,
                decision_history=[],
                version_evolution=[],
                artifact_index=[],
                key_conversations=[]
            )

        decision_history = [
            DecisionRecord(**record) if isinstance(record, dict) else record
            for record in memory_data.get("decision_history", [])
        ]

        version_evolution = [
            VersionEvolution(**record) if isinstance(record, dict) else record
            for record in memory_data.get("version_evolution", [])
        ]

        return ProjectMemory(
            project_id=project_id,
            decision_history=decision_history,
            version_evolution=version_evolution,
            artifact_index=memory_data.get("artifact_index", []),
            key_conversations=memory_data.get("key_conversations", []),
            updated_at=datetime.fromisoformat(memory_data.get("updated_at", _utc_now().isoformat()))
        )

    async def add_decision(
        self,
        project_id: str,
        workspace_id: str,
        decision: str,
        rationale: str,
        alternatives_considered: Optional[List[str]] = None,
        decision_maker: Optional[str] = None
    ) -> ProjectMemory:
        """
        Add a decision record to project memory

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            decision: Decision made
            rationale: Reasoning behind the decision
            alternatives_considered: Alternatives that were considered
            decision_maker: Who made the decision

        Returns:
            Updated ProjectMemory instance
        """
        import uuid
        memory = await self.get_project_memory(project_id, workspace_id)

        decision_record = DecisionRecord(
            id=f"dec_{uuid.uuid4().hex[:12]}",
            decision=decision,
            rationale=rationale,
            alternatives_considered=alternatives_considered,
            decision_maker=decision_maker
        )

        memory.decision_history.append(decision_record)
        memory.updated_at = _utc_now()

        await self._save_project_memory(project_id, workspace_id, memory)

        logger.info(f"Added decision to project {project_id}: {decision}")
        return memory

    async def add_version(
        self,
        project_id: str,
        workspace_id: str,
        version: str,
        summary: str,
        key_changes: List[str],
        artifacts: Optional[List[str]] = None
    ) -> ProjectMemory:
        """
        Add a version evolution record

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            version: Version identifier
            summary: Version summary
            key_changes: Key changes in this version
            artifacts: Artifacts in this version

        Returns:
            Updated ProjectMemory instance
        """
        memory = await self.get_project_memory(project_id, workspace_id)

        version_record = VersionEvolution(
            version=version,
            summary=summary,
            key_changes=key_changes,
            artifacts=artifacts
        )

        memory.version_evolution.append(version_record)
        memory.updated_at = _utc_now()

        await self._save_project_memory(project_id, workspace_id, memory)

        logger.info(f"Added version {version} to project {project_id}")
        return memory

    async def add_key_conversation(
        self,
        project_id: str,
        workspace_id: str,
        conversation_summary: str
    ) -> ProjectMemory:
        """
        Add a key conversation summary

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            conversation_summary: Summary of the conversation

        Returns:
            Updated ProjectMemory instance
        """
        memory = await self.get_project_memory(project_id, workspace_id)
        memory.key_conversations.append(conversation_summary)
        memory.updated_at = _utc_now()

        await self._save_project_memory(project_id, workspace_id, memory)

        return memory

    async def _save_project_memory(
        self,
        project_id: str,
        workspace_id: str,
        memory: ProjectMemory
    ):
        """Save project memory to project metadata"""
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        project.metadata = project.metadata or {}
        project.metadata["project_memory"] = {
            "decision_history": [
                {
                    "id": d.id,
                    "timestamp": d.timestamp.isoformat(),
                    "decision": d.decision,
                    "rationale": d.rationale,
                    "alternatives_considered": d.alternatives_considered,
                    "decision_maker": d.decision_maker
                }
                for d in memory.decision_history
            ],
            "version_evolution": [
                {
                    "version": v.version,
                    "timestamp": v.timestamp.isoformat(),
                    "summary": v.summary,
                    "key_changes": v.key_changes,
                    "artifacts": v.artifacts
                }
                for v in memory.version_evolution
            ],
            "artifact_index": memory.artifact_index,
            "key_conversations": memory.key_conversations,
            "updated_at": memory.updated_at.isoformat()
        }
        await self.project_manager.update_project(project)

    def format_for_context(self, memory: ProjectMemory) -> str:
        """
        Format project memory for LLM context injection

        Args:
            memory: ProjectMemory instance

        Returns:
            Formatted context string
        """
        parts = []

        if memory.decision_history:
            parts.append("## Recent Decisions:")
            for decision in memory.decision_history[-3:]:
                parts.append(f"- {decision.decision}")
                parts.append(f"  Rationale: {decision.rationale}")

        if memory.version_evolution:
            parts.append("\n## Version Evolution:")
            for version in memory.version_evolution[-3:]:
                parts.append(f"- {version.version}: {version.summary}")
                if version.key_changes:
                    for change in version.key_changes[:3]:
                        parts.append(f"  - {change}")

        if memory.key_conversations:
            parts.append("\n## Key Conversations:")
            for conv in memory.key_conversations[-3:]:
                parts.append(f"- {conv}")

        return "\n".join(parts) if parts else ""

