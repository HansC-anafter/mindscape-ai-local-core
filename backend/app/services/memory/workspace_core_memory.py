"""
Workspace Core Memory Service

Manages long-term workspace memory including:
- Brand identity and voice
- Style guidelines and constraints
- Long-term values and goals
- Important milestones and learnings
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class WorkspaceCoreMemory(BaseModel):
    """
    Workspace Core Memory - long-term workspace context

    Stores stable, long-term information about the workspace:
    - Brand identity and voice guidelines
    - Style constraints and preferences
    - Important milestones and learnings
    - Core values and objectives
    """

    workspace_id: str = Field(..., description="Workspace ID")
    brand_identity: Optional[Dict[str, Any]] = Field(
        None,
        description="Brand identity information (name, values, positioning)"
    )
    voice_and_tone: Optional[Dict[str, Any]] = Field(
        None,
        description="Voice and tone guidelines (formal/informal, friendly/professional)"
    )
    style_constraints: Optional[List[str]] = Field(
        None,
        description="Style constraints and preferences (colors, fonts, dos/don'ts)"
    )
    important_milestones: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Important milestones and achievements"
    )
    learnings: Optional[List[str]] = Field(
        None,
        description="Key learnings and insights from past projects"
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WorkspaceCoreMemoryService:
    """
    Service for managing workspace core memory

    Provides methods to read and update workspace core memory,
    which persists across all projects and conversations.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize Workspace Core Memory Service

        Args:
            store: MindscapeStore instance
        """
        self.store = store

    async def get_core_memory(self, workspace_id: str) -> WorkspaceCoreMemory:
        """
        Get workspace core memory

        Loads core memory from workspace metadata, or creates default if not exists.

        Args:
            workspace_id: Workspace ID

        Returns:
            WorkspaceCoreMemory instance
        """
        workspace = self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        memory_data = workspace.metadata.get("core_memory", {})

        if not memory_data:
            return WorkspaceCoreMemory(
                workspace_id=workspace_id,
                brand_identity=None,
                voice_and_tone=None,
                style_constraints=None,
                important_milestones=None,
                learnings=None
            )

        return WorkspaceCoreMemory(
            workspace_id=workspace_id,
            brand_identity=memory_data.get("brand_identity"),
            voice_and_tone=memory_data.get("voice_and_tone"),
            style_constraints=memory_data.get("style_constraints"),
            important_milestones=memory_data.get("important_milestones"),
            learnings=memory_data.get("learnings"),
            updated_at=datetime.fromisoformat(memory_data.get("updated_at", datetime.utcnow().isoformat()))
        )

    async def update_core_memory(
        self,
        workspace_id: str,
        brand_identity: Optional[Dict[str, Any]] = None,
        voice_and_tone: Optional[Dict[str, Any]] = None,
        style_constraints: Optional[List[str]] = None,
        important_milestones: Optional[List[Dict[str, Any]]] = None,
        learnings: Optional[List[str]] = None
    ) -> WorkspaceCoreMemory:
        """
        Update workspace core memory

        Merges new values with existing memory. None values are not updated.

        Args:
            workspace_id: Workspace ID
            brand_identity: Brand identity information
            voice_and_tone: Voice and tone guidelines
            style_constraints: Style constraints and preferences
            important_milestones: Important milestones (appended to existing)
            learnings: Learnings (appended to existing)

        Returns:
            Updated WorkspaceCoreMemory instance
        """
        memory = await self.get_core_memory(workspace_id)

        if brand_identity is not None:
            memory.brand_identity = brand_identity
        if voice_and_tone is not None:
            memory.voice_and_tone = voice_and_tone
        if style_constraints is not None:
            memory.style_constraints = style_constraints
        if important_milestones is not None:
            existing_milestones = memory.important_milestones or []
            memory.important_milestones = existing_milestones + important_milestones
        if learnings is not None:
            existing_learnings = memory.learnings or []
            memory.learnings = existing_learnings + learnings

        memory.updated_at = datetime.utcnow()

        workspace = self.store.get_workspace(workspace_id)
        workspace.metadata = workspace.metadata or {}
        workspace.metadata["core_memory"] = {
            "brand_identity": memory.brand_identity,
            "voice_and_tone": memory.voice_and_tone,
            "style_constraints": memory.style_constraints,
            "important_milestones": memory.important_milestones,
            "learnings": memory.learnings,
            "updated_at": memory.updated_at.isoformat()
        }
        self.store.update_workspace(workspace)

        logger.info(f"Updated core memory for workspace {workspace_id}")
        return memory

    async def add_milestone(
        self,
        workspace_id: str,
        milestone: Dict[str, Any]
    ) -> WorkspaceCoreMemory:
        """
        Add an important milestone to workspace core memory

        Args:
            workspace_id: Workspace ID
            milestone: Milestone information (should include title, date, description)

        Returns:
            Updated WorkspaceCoreMemory instance
        """
        memory = await self.get_core_memory(workspace_id)
        existing_milestones = memory.important_milestones or []
        existing_milestones.append({
            **milestone,
            "added_at": datetime.utcnow().isoformat()
        })
        return await self.update_core_memory(
            workspace_id=workspace_id,
            important_milestones=existing_milestones
        )

    async def add_learning(
        self,
        workspace_id: str,
        learning: str
    ) -> WorkspaceCoreMemory:
        """
        Add a learning or insight to workspace core memory

        Args:
            workspace_id: Workspace ID
            learning: Learning or insight text

        Returns:
            Updated WorkspaceCoreMemory instance
        """
        memory = await self.get_core_memory(workspace_id)
        existing_learnings = memory.learnings or []
        existing_learnings.append(learning)
        return await self.update_core_memory(
            workspace_id=workspace_id,
            learnings=existing_learnings
        )

    def format_for_context(self, memory: WorkspaceCoreMemory) -> str:
        """
        Format core memory for LLM context injection

        Args:
            memory: WorkspaceCoreMemory instance

        Returns:
            Formatted context string
        """
        parts = []

        if memory.brand_identity:
            parts.append("## Brand Identity:")
            for key, value in memory.brand_identity.items():
                parts.append(f"- {key}: {value}")

        if memory.voice_and_tone:
            parts.append("\n## Voice and Tone:")
            for key, value in memory.voice_and_tone.items():
                parts.append(f"- {key}: {value}")

        if memory.style_constraints:
            parts.append("\n## Style Constraints:")
            for constraint in memory.style_constraints:
                parts.append(f"- {constraint}")

        if memory.important_milestones:
            parts.append("\n## Important Milestones:")
            for milestone in memory.important_milestones[-5:]:
                title = milestone.get("title", "Untitled")
                date = milestone.get("date", "")
                description = milestone.get("description", "")
                parts.append(f"- {title} ({date}): {description}")

        if memory.learnings:
            parts.append("\n## Key Learnings:")
            for learning in memory.learnings[-5:]:
                parts.append(f"- {learning}")

        return "\n".join(parts) if parts else ""

