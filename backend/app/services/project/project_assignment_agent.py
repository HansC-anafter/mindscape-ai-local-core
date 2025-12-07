"""
Project Assignment Agent

Suggests human owner and AI PM assignments for new Projects based on
workspace members, past projects, and project type.
"""

import json
import logging
from typing import Optional, Dict, Any
from backend.app.models.project import Project, ProjectAssignmentOutput
from backend.app.models.workspace import Workspace
from backend.app.services.agent_runner import LLMProviderManager
from backend.app.shared.llm_provider_helper import (
    get_llm_provider_from_settings,
    create_llm_provider_manager,
    get_model_name_from_chat_model
)

logger = logging.getLogger(__name__)


class ProjectAssignmentAgent:
    """
    Project Assignment Agent - suggests PM assignments for Projects

    Analyzes project requirements and workspace context to suggest
    appropriate human owner and AI PM assignments.
    """

    def __init__(self, llm_provider=None):
        """
        Initialize Project Assignment Agent

        Args:
            llm_provider: Optional LLM provider (will be created from settings if None)
        """
        self.llm_provider = llm_provider
        if llm_provider is None:
            llm_manager = create_llm_provider_manager()
            self.llm_provider = get_llm_provider_from_settings(llm_manager)

    async def suggest_assignment(
        self,
        project: Project,
        workspace: Workspace
    ) -> ProjectAssignmentOutput:
        """
        Suggest human owner and AI PM for a project

        Args:
            project: Project object
            workspace: Workspace object

        Returns:
            ProjectAssignmentOutput with suggested assignments
        """
        try:
            # Get workspace members (simplified - would need member service)
            workspace_members = []  # TODO: Get from workspace/member service

            # Build assignment prompt
            prompt = f"""
Analyze the following new project and suggest appropriate assignments.

Project:
- Type: {project.type}
- Title: {project.title}
- Initiator: {project.initiator_user_id}

Workspace:
- Mode: {workspace.mode or 'general'}
- Title: {workspace.title}

Workspace Members: {self._format_members(workspace_members)}

Past Projects: {self._get_past_projects_summary(workspace)}  # TODO: Implement

Suggest:
1. Human Owner: Best person to own this project (consider skills, experience, current workload)
2. AI PM: Best AI team to manage this project workflow

Common AI PM mappings:
- web_page -> ai_team.web_design
- seo_campaign -> ai_team.seo_chain_agent
- writing_project/book -> ai_team.book_companion
- course -> ai_team.course_production
- campaign -> ai_team.campaign_manager

Respond in JSON format:
{{
    "suggested_human_owner": {{
        "user_id": "user_id",
        "reason": "Brief reason"
    }},
    "suggested_ai_pm_id": "ai_team.identifier",
    "reasoning": "Overall reasoning for assignments"
}}
"""

            # Call LLM
            messages = [
                {
                    "role": "system",
                    "content": "You are a project assignment assistant. Analyze projects and suggest appropriate human and AI PM assignments. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            # Get model name from system settings
            model_name = get_model_name_from_chat_model() or "gemini-pro"
            response = await self.llm_provider.chat_completion(messages, model=model_name)
            result_text = response.content if hasattr(response, 'content') else str(response)

            # Parse response
            assignment = self._parse_response(result_text)
            return assignment

        except Exception as e:
            logger.error(f"Project assignment failed: {e}", exc_info=True)
            # Return default assignment
            return ProjectAssignmentOutput(
                suggested_human_owner=None,
                suggested_ai_pm_id=self._get_default_ai_pm(project.type),
                reasoning="Assignment failed, using default"
            )

    def _format_members(self, members: list) -> str:
        """Format workspace members for prompt"""
        if not members:
            return "No members listed"
        # TODO: Format member info (roles, skills, past projects)
        return f"{len(members)} members available"

    def _get_past_projects_summary(self, workspace: Workspace) -> str:
        """Get summary of past projects in workspace"""
        # TODO: Query past projects from database
        return "No past projects data available"

    def _get_default_ai_pm(self, project_type: str) -> Optional[str]:
        """Get default AI PM ID based on project type"""
        mapping = {
            "web_page": "ai_team.web_design",
            "book": "ai_team.book_companion",
            "course": "ai_team.course_production",
            "campaign": "ai_team.campaign_manager",
            "video_series": "ai_team.video_production"
        }
        return mapping.get(project_type, "ai_team.general")

    def _parse_response(self, response_text: str) -> ProjectAssignmentOutput:
        """Parse LLM response into ProjectAssignmentOutput"""
        try:
            # Extract JSON from response
            text = response_text.strip()
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()

            data = json.loads(text)

            return ProjectAssignmentOutput(
                suggested_human_owner=data.get("suggested_human_owner"),
                suggested_ai_pm_id=data.get("suggested_ai_pm_id"),
                reasoning=data.get("reasoning", "No reasoning provided")
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse assignment response: {e}")
            return ProjectAssignmentOutput(
                suggested_human_owner=None,
                suggested_ai_pm_id=None,
                reasoning=f"Parse error: {e}"
            )

