"""
Member Profile Memory Service

Manages member-specific memory including:
- Skills and expertise
- Preferences and working style
- Past project experiences
- Communication preferences
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class ProjectExperience(BaseModel):
    """Record of member's experience in a project"""

    project_id: str = Field(..., description="Project ID")
    project_type: str = Field(..., description="Project type")
    role: str = Field(..., description="Role in the project")
    contributions: Optional[List[str]] = Field(None, description="Key contributions")
    learnings: Optional[List[str]] = Field(None, description="Learnings from this project")
    completed_at: Optional[datetime] = Field(None, description="Project completion date")


class MemberProfileMemory(BaseModel):
    """
    Member Profile Memory - individual member context

    Stores member-specific information that helps personalize interactions:
    - Skills and expertise areas
    - Working style preferences
    - Past project experiences
    - Communication preferences
    """

    user_id: str = Field(..., description="User ID")
    workspace_id: str = Field(..., description="Workspace ID")
    skills: List[str] = Field(default_factory=list, description="Skills and expertise areas")
    preferences: Optional[Dict[str, Any]] = Field(
        None,
        description="Preferences (working style, communication, tools)"
    )
    project_experiences: List[ProjectExperience] = Field(
        default_factory=list,
        description="Past project experiences"
    )
    learnings: Optional[List[str]] = Field(None, description="Key learnings and insights")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MemberProfileMemoryService:
    """
    Service for managing member profile memory

    Provides methods to read and update member-specific memory,
    which helps personalize interactions and suggestions.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize Member Profile Memory Service

        Args:
            store: MindscapeStore instance
        """
        self.store = store

    async def get_member_memory(
        self,
        user_id: str,
        workspace_id: str
    ) -> MemberProfileMemory:
        """
        Get member profile memory

        Loads memory from profile metadata, or creates default if not exists.

        Args:
            user_id: User ID
            workspace_id: Workspace ID

        Returns:
            MemberProfileMemory instance
        """
        profile = self.store.get_profile(user_id)
        if not profile:
            return MemberProfileMemory(
                user_id=user_id,
                workspace_id=workspace_id,
                skills=[],
                preferences=None,
                project_experiences=[],
                learnings=None
            )

        workspace_memory = profile.metadata.get("workspace_memories", {}).get(workspace_id, {})

        project_experiences = [
            ProjectExperience(**exp) if isinstance(exp, dict) else exp
            for exp in workspace_memory.get("project_experiences", [])
        ]

        return MemberProfileMemory(
            user_id=user_id,
            workspace_id=workspace_id,
            skills=workspace_memory.get("skills", []),
            preferences=workspace_memory.get("preferences"),
            project_experiences=project_experiences,
            learnings=workspace_memory.get("learnings"),
            updated_at=datetime.fromisoformat(
                workspace_memory.get("updated_at", datetime.utcnow().isoformat())
            )
        )

    async def update_member_memory(
        self,
        user_id: str,
        workspace_id: str,
        skills: Optional[List[str]] = None,
        preferences: Optional[Dict[str, Any]] = None,
        learnings: Optional[List[str]] = None
    ) -> MemberProfileMemory:
        """
        Update member profile memory

        Merges new values with existing memory. None values are not updated.

        Args:
            user_id: User ID
            workspace_id: Workspace ID
            skills: Skills and expertise areas
            preferences: Preferences dictionary
            learnings: Learnings (appended to existing)

        Returns:
            Updated MemberProfileMemory instance
        """
        memory = await self.get_member_memory(user_id, workspace_id)

        if skills is not None:
            memory.skills = skills
        if preferences is not None:
            memory.preferences = {**(memory.preferences or {}), **preferences}
        if learnings is not None:
            existing_learnings = memory.learnings or []
            memory.learnings = existing_learnings + learnings

        memory.updated_at = datetime.utcnow()

        profile = self.store.get_profile(user_id)
        if not profile:
            logger.warning(f"Profile {user_id} not found, cannot update memory")
            return memory

        profile.metadata = profile.metadata or {}
        if "workspace_memories" not in profile.metadata:
            profile.metadata["workspace_memories"] = {}

        profile.metadata["workspace_memories"][workspace_id] = {
            "skills": memory.skills,
            "preferences": memory.preferences,
            "project_experiences": [
                {
                    "project_id": exp.project_id,
                    "project_type": exp.project_type,
                    "role": exp.role,
                    "contributions": exp.contributions,
                    "learnings": exp.learnings,
                    "completed_at": exp.completed_at.isoformat() if exp.completed_at else None
                }
                for exp in memory.project_experiences
            ],
            "learnings": memory.learnings,
            "updated_at": memory.updated_at.isoformat()
        }

        self.store.update_profile(profile)

        logger.info(f"Updated member memory for user {user_id} in workspace {workspace_id}")
        return memory

    async def add_project_experience(
        self,
        user_id: str,
        workspace_id: str,
        project_id: str,
        project_type: str,
        role: str,
        contributions: Optional[List[str]] = None,
        learnings: Optional[List[str]] = None
    ) -> MemberProfileMemory:
        """
        Add a project experience record

        Args:
            user_id: User ID
            workspace_id: Workspace ID
            project_id: Project ID
            project_type: Project type
            role: Role in the project
            contributions: Key contributions
            learnings: Learnings from this project

        Returns:
            Updated MemberProfileMemory instance
        """
        memory = await self.get_member_memory(user_id, workspace_id)

        experience = ProjectExperience(
            project_id=project_id,
            project_type=project_type,
            role=role,
            contributions=contributions,
            learnings=learnings
        )

        memory.project_experiences.append(experience)
        memory.updated_at = datetime.utcnow()

        profile = self.store.get_profile(user_id)
        if profile:
            profile.metadata = profile.metadata or {}
            if "workspace_memories" not in profile.metadata:
                profile.metadata["workspace_memories"] = {}

            if workspace_id not in profile.metadata["workspace_memories"]:
                profile.metadata["workspace_memories"][workspace_id] = {}

            existing_experiences = profile.metadata["workspace_memories"][workspace_id].get("project_experiences", [])
            existing_experiences.append({
                "project_id": project_id,
                "project_type": project_type,
                "role": role,
                "contributions": contributions,
                "learnings": learnings,
                "completed_at": None
            })
            profile.metadata["workspace_memories"][workspace_id]["project_experiences"] = existing_experiences
            profile.metadata["workspace_memories"][workspace_id]["updated_at"] = memory.updated_at.isoformat()

            self.store.update_profile(profile)

        logger.info(f"Added project experience for user {user_id}: {project_id}")
        return memory

    def format_for_context(
        self,
        memory: MemberProfileMemory,
        include_experiences: bool = False
    ) -> str:
        """
        Format member memory for LLM context injection

        Args:
            memory: MemberProfileMemory instance
            include_experiences: Whether to include project experiences

        Returns:
            Formatted context string
        """
        parts = []

        if memory.skills:
            parts.append(f"## Skills: {', '.join(memory.skills[:5])}")

        if memory.preferences:
            parts.append("\n## Preferences:")
            for key, value in list(memory.preferences.items())[:3]:
                parts.append(f"- {key}: {value}")

        if include_experiences and memory.project_experiences:
            parts.append("\n## Recent Projects:")
            for exp in memory.project_experiences[-3:]:
                parts.append(f"- {exp.project_type} ({exp.role})")

        return "\n".join(parts) if parts else ""

