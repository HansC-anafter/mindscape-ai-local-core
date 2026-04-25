"""
Project Assignment Agent

Suggests human owner and AI PM assignments for new Projects based on
workspace members, past projects, and project type.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from backend.app.models.project import Project, ProjectAssignmentOutput
from backend.app.models.workspace import Workspace
from backend.app.services.llm.workspace_routed_chat import (
    chat_completion_with_workspace_route,
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
            llm_provider: Deprecated direct provider override. Governed routing is always used.
        """
        self.llm_provider = llm_provider

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

            data = await self._run_governed_json_request(
                workspace_id=getattr(workspace, "id", None),
                messages=messages,
                purpose="project_assignment_suggest",
                stage_name="scope_decision",
            )
            return self._parse_response_data(data)

        except Exception as e:
            logger.error(f"Project assignment failed: {e}", exc_info=True)
            return ProjectAssignmentOutput(
                suggested_human_owner=None,
                suggested_ai_pm_id=None,
                reasoning=f"Assignment unavailable: {e}",
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

    @staticmethod
    def _coerce_response_text(response: Any) -> str:
        if isinstance(response, dict):
            if "content" in response:
                return str(response.get("content") or "")
            return json.dumps(response, ensure_ascii=False)
        return response.content if hasattr(response, "content") else str(response)

    @classmethod
    def _extract_json_payload(cls, response_text: str) -> Dict[str, Any]:
        try:
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
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse assignment response: {e}")
            return {}

    @classmethod
    def _parse_response_data(cls, data: Dict[str, Any]) -> ProjectAssignmentOutput:
        return ProjectAssignmentOutput(
            suggested_human_owner=data.get("suggested_human_owner"),
            suggested_ai_pm_id=data.get("suggested_ai_pm_id"),
            reasoning=data.get("reasoning", "No reasoning provided"),
        )

    async def _run_governed_json_request(
        self,
        *,
        workspace_id: Optional[str],
        messages: List[Dict[str, str]],
        purpose: str,
        stage_name: str,
    ) -> Dict[str, Any]:
        response = await chat_completion_with_workspace_route(
            messages=messages,
            workspace_id=workspace_id,
            purpose=purpose,
            stage_name=stage_name,
            risk_level="read",
        )
        return self._extract_json_payload(self._coerce_response_text(response))

    async def assign_project_for_message(
        self,
        message: str,
        workspace_id: str,
        project_candidates: List[Dict[str, Any]],
        last_project_id: Optional[str] = None,
        conversation_context: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Assign project for a new message

        Args:
            message: User message
            workspace_id: Workspace ID
            project_candidates: List of candidate projects from ProjectIndex
            last_project_id: Last project ID from conversation context
            conversation_context: Recent conversation history

        Returns:
            {
                "project_id": "...",
                "relation": "same_project" | "new_project" | "ambiguous",
                "confidence": 0.86,
                "reasoning": "...",
                "candidates": [...]
            }
        """
        try:
            # Format candidates for prompt
            candidates_str = self._format_project_candidates(project_candidates)
            context_str = self._format_conversation_context(conversation_context or [])

            # Build assignment prompt
            prompt = f"""
Analyze the following user message and determine which Project it belongs to.

User message: {message}

Recent conversation:
{context_str}

Candidate Projects:
{candidates_str}

Last active project: {last_project_id or "None"}

Determine:
1. relation: One of:
   - "same_project": This message is clearly a continuation of an existing project
   - "new_project": This message is clearly a request for a completely new project
   - "ambiguous": Cannot determine with high confidence

2. If relation is "same_project":
   - project_id: Which project ID from candidates (or last_project_id if it matches)
   - confidence: Confidence score (0.0-1.0)
   - reasoning: Why this is the same project

3. If relation is "new_project":
   - project_id: null
   - confidence: Confidence score (0.0-1.0)
   - reasoning: Why this is a new project

4. If relation is "ambiguous":
   - project_id: Best guess project_id (or null if truly ambiguous)
   - confidence: Low confidence score (< 0.7)
   - reasoning: Why it's ambiguous

IMPORTANT RULES:
- If a new task is semantically highly similar to an existing project AND the conversation context points to that project, in 95% of cases it should be "same_project"
- Only mark as "new_project" if the user explicitly requests a completely different work item
- Be conservative: when in doubt, prefer "same_project" over "new_project"

Respond in JSON format:
{{
    "relation": "same_project|new_project|ambiguous",
    "project_id": "project_id or null",
    "confidence": 0.0-1.0,
    "reasoning": "Brief reasoning",
    "selected_candidate": {{
        "project_id": "...",
        "similarity": 0.0-1.0
    }}
}}
"""

            # Call LLM
            messages = [
                {
                    "role": "system",
                    "content": "You are a project assignment assistant. Analyze messages to determine project assignment. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            decision = self._parse_assignment_response(
                await self._run_governed_json_request(
                    workspace_id=workspace_id,
                    messages=messages,
                    purpose="project_assignment_message",
                    stage_name="execution_selection",
                )
            )
            # Add candidates to decision
            decision["candidates"] = project_candidates
            return decision

        except Exception as e:
            logger.error(f"Project assignment failed: {e}", exc_info=True)
            # Fallback: use last_project_id if available
            return {
                "relation": "ambiguous",
                "project_id": last_project_id,
                "confidence": 0.5,
                "reasoning": f"Assignment failed: {e}",
                "candidates": project_candidates
            }

    def _format_project_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        """Format project candidates for prompt"""
        if not candidates:
            return "No candidate projects available"

        lines = []
        for i, candidate in enumerate(candidates, 1):
            project = candidate.get("project")
            similarity = candidate.get("similarity", 0.0)

            if project:
                project_id = getattr(project, "id", candidate.get("project_id", "unknown"))
                project_title = getattr(project, "title", "Unknown")
                project_type = getattr(project, "type", "unknown")
                lines.append(
                    f"{i}. Project ID: {project_id}\n"
                    f"   Title: {project_title}\n"
                    f"   Type: {project_type}\n"
                    f"   Similarity: {similarity:.2f}"
                )
            else:
                project_id = candidate.get("project_id", "unknown")
                lines.append(f"{i}. Project ID: {project_id} (similarity: {similarity:.2f})")

        return "\n".join(lines)

    def _format_conversation_context(self, context: List[Dict[str, str]]) -> str:
        """Format conversation context for prompt"""
        if not context:
            return "No recent conversation context"

        lines = []
        for msg in context:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role}: {content[:200]}")  # Truncate long messages

        return "\n".join(lines)

    def _parse_assignment_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM response into assignment decision"""
        try:
            return {
                "relation": data.get("relation", "ambiguous"),
                "project_id": data.get("project_id"),
                "confidence": float(data.get("confidence", 0.5)),
                "reasoning": data.get("reasoning", "No reasoning provided"),
                "selected_candidate": data.get("selected_candidate", {})
            }

        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse assignment response: {e}")
            return {
                "relation": "ambiguous",
                "project_id": None,
                "confidence": 0.5,
                "reasoning": f"Parse error: {e}",
                "selected_candidate": {}
            }
