"""
Project Detector service

Detects if a conversation message suggests creating a new Project.
Uses LLM to analyze user intent and determine if a project should be created.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from backend.app.models.project import ProjectSuggestion
from backend.app.models.workspace import Workspace
from backend.app.services.llm.workspace_routed_chat import (
    chat_completion_with_workspace_route,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class ProjectDetector:
    """
    Project Detector - detects if conversation suggests creating a Project

    Analyzes user messages in workspace lobby conversations to determine
    if they require creating a new Project (vs quick_task or micro_flow).
    """

    def __init__(self, llm_provider=None):
        """
        Initialize Project Detector

        Args:
            llm_provider: Deprecated direct provider override. Governed routing is always used.
        """
        self.llm_provider = llm_provider

    async def detect(
        self,
        message: str,
        conversation_context: List[Dict[str, str]],
        workspace: Workspace,
        available_playbooks: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[ProjectSuggestion]:
        """
        Detect if message suggests creating a Project

        Args:
            message: Current user message
            conversation_context: Recent conversation history (list of {role, content})
            workspace: Workspace object

        Returns:
            ProjectSuggestion if project should be created, None otherwise
        """
        try:
            # Format conversation context
            context_str = self._format_conversation_context(conversation_context)

            # Format available playbooks for prompt
            playbooks_str = "No available playbooks."
            if available_playbooks:
                playbooks_str = "\n".join(
                    [
                        f"- {pb.get('playbook_code')}: {pb.get('name')} - {pb.get('description')}"
                        for pb in available_playbooks
                    ]
                )

            # Build detection prompt
            prompt = f"""
Analyze the following conversation and determine if a new Project should be created.

Workspace type: {workspace.mode or 'general'}
User message: {message}

Recent conversation:
{context_str}

## Available Playbooks (Capabilities):
{playbooks_str}

## Instructions:
Determine the best way to handle this request. Choose one of the following modes:
- "quick_task": Simple query that can be answered immediately (e.g., "What time is it?", "Hello").
- "micro_flow": Brief task sequence that doesn't need full project setup.
- "project": Requires a dedicated project with a flow of tasks. **Almost all complex requests like "analyze something", "generate a plan", "execute a campaign" should be projects.**

If mode is "project", provide:
1. `project_type`: Use a descriptive ID (e.g., "market_analysis", "content_generation", "ig_analysis").
2. `project_title`: A concise name for the project.
3. `playbook_sequence`: An array of playbook codes from the "Available Playbooks" list above that should be executed. **If the user's request matches any available playbook capability, INCLUDE IT in the sequence.**
4. `initial_spec_md`: Initial specification in markdown format.
5. `confidence`: Your confidence (0.0-1.0).

## Rules:
- **playbook_sequence MUST ONLY contain codes from the "Available Playbooks" list.**
- If no playbook matches, set `playbook_sequence` to an empty list `[]`, but keep mode as "project" if it's a complex multi-step request.
- Respond in {workspace.default_locale or 'zh-TW'}.

Respond in JSON format:
{{
    "mode": "quick_task|micro_flow|project",
    "project_type": "string",
    "project_title": "string",
    "playbook_sequence": ["code1", "code2", ...],
    "initial_spec_md": "string",
    "confidence": 0.0-1.0
}}
"""

            # Evidence Logging
            try:
                log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n==== DETECT EVIDENCE {_utc_now()} ====\n")
                    f.write(f"Workspace: {workspace.id}\n")
                    f.write(
                        f"Available Playbooks: {len(available_playbooks) if available_playbooks else 0}\n"
                    )
                    f.write(f"Prompt:\n{prompt}\n")
                    f.write("==========================================\n")
            except Exception:
                pass

            # Call LLM
            messages = [
                {
                    "role": "system",
                    "content": "You are a project detection assistant. Analyze conversations to determine if a new project should be created. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            # Evidence Logging
            decision_log: list[dict[str, Any]] = []
            try:
                from datetime import datetime, timezone

                log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n==== DETECT LLM CALL START {_utc_now()} ====\n")
                    f.write(f"Route Decisions: {json.dumps(decision_log, ensure_ascii=False)}\n")
                    f.write("==========================================\n")
            except Exception:
                pass

            response = await chat_completion_with_workspace_route(
                messages=messages,
                workspace_id=getattr(workspace, "id", None),
                purpose="project_detector_detect",
                stage_name="scope_decision",
                decision_log=decision_log,
                risk_level="read",
            )
            result_text = self._coerce_response_text(response)

            # Evidence Logging
            try:
                from datetime import datetime, timezone

                log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n==== DETECT LLM CALL SUCCESS {_utc_now()} ====\n"
                    )
                    f.write("==========================================\n")
            except Exception:
                pass

            # Parse response
            suggestion = self._parse_response_data(
                self._extract_json_payload(result_text)
            )

            # Evidence Logging
            try:
                from datetime import datetime, timezone

                log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n==== DETECT RESPONSE {_utc_now()} ====\n")
                    f.write(f"Response:\n{result_text}\n")
                    f.write(
                        f"Parsed Mode: {suggestion.mode if suggestion else 'None'}\n"
                    )
                    f.write(
                        f"Parsed Sequence: {suggestion.playbook_sequence if suggestion else '[]'}\n"
                    )
                    f.write("==========================================\n")
            except Exception:
                pass

            return suggestion

        except Exception as e:
            logger.error(f"Project detection failed: {e}", exc_info=True)
            # Evidence Logging
            try:
                from datetime import datetime, timezone

                log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n==== DETECT EXCEPTION {_utc_now()} ====\n")
                    f.write(f"Error: {str(e)}\n")
                    f.write("==========================================\n")
            except Exception:
                pass
            return None

    def _format_conversation_context(self, context: List[Dict[str, str]]) -> str:
        """Format conversation context for prompt"""
        if not context:
            return "No recent conversation."

        formatted = []
        for msg in context[-10:]:  # Last 10 messages
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                formatted.append(f"{role}: {content}")

        return "\n".join(formatted) if formatted else "No recent conversation."

    async def check_duplicate(
        self,
        suggested_project: ProjectSuggestion,
        existing_projects: List[Any],
        workspace: Workspace,
    ) -> Optional[Any]:
        """
        Use LLM to check if suggested project is a duplicate of existing projects

        Args:
            suggested_project: Project suggestion from detector
            existing_projects: List of existing projects
            workspace: Workspace object

        Returns:
            Duplicate project if found, None otherwise
        """
        if not existing_projects or not suggested_project.project_title:
            return None

        try:
            # Format existing projects for LLM
            existing_projects_str = "\n".join(
                [
                    f"- {p.title} (type: {p.type}, id: {p.id})"
                    for p in existing_projects[:10]  # Limit to 10 for context
                ]
            )

            prompt = f"""
Analyze if the suggested project is a duplicate of any existing project.

Suggested project:
- Title: {suggested_project.project_title}
- Type: {suggested_project.project_type or 'not specified'}
- Description: {suggested_project.initial_spec_md[:200] if suggested_project.initial_spec_md else 'No description'}

Existing projects in workspace:
{existing_projects_str}

Determine if the suggested project is:
1. A duplicate of an existing project (same or very similar work)
2. A new project (different work)

If it's a duplicate, return the project ID. If it's new, return null.

Respond in JSON format:
{{
    "is_duplicate": true/false,
    "duplicate_project_id": "project_id_or_null",
    "reasoning": "brief explanation"
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are a project duplicate detection assistant. Analyze if a suggested project is a duplicate of existing projects. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await chat_completion_with_workspace_route(
                messages=messages,
                workspace_id=getattr(workspace, "id", None),
                purpose="project_detector_duplicate_check",
                stage_name="scope_decision",
                risk_level="read",
            )
            data = self._extract_json_payload(self._coerce_response_text(response)) or {}

            if data.get("is_duplicate") and data.get("duplicate_project_id"):
                project_id = data.get("duplicate_project_id")
                # Find the project in existing_projects
                for p in existing_projects:
                    if p.id == project_id:
                        logger.info(
                            f"LLM detected duplicate project: {project_id} - {data.get('reasoning', '')}"
                        )
                        return p
                logger.warning(
                    f"LLM returned duplicate_project_id {project_id} but project not found in existing_projects"
                )

            return None

        except Exception as e:
            logger.warning(f"Failed to check duplicate using LLM: {e}")
            return None

    @staticmethod
    def _coerce_response_text(response: Any) -> str:
        if isinstance(response, dict):
            if "content" in response:
                return str(response.get("content") or "")
            return json.dumps(response, ensure_ascii=False)
        return response.content if hasattr(response, "content") else str(response)

    @staticmethod
    def _extract_json_payload(response_text: str) -> Optional[Dict[str, Any]]:
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
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse project detection response: %s", exc)
            return None

    @staticmethod
    def _parse_response_data(data: Optional[Dict[str, Any]]) -> Optional[ProjectSuggestion]:
        """Parse governed JSON payload into ProjectSuggestion."""
        if not data or data.get("mode") != "project":
            return None

        playbook_sequence = data.get("playbook_sequence", [])
        if not isinstance(playbook_sequence, list):
            playbook_sequence = []

        return ProjectSuggestion(
            mode=data.get("mode", "quick_task"),
            project_type=data.get("project_type"),
            project_title=data.get("project_title"),
            playbook_sequence=playbook_sequence,
            initial_spec_md=data.get("initial_spec_md"),
            confidence=data.get("confidence", 0.0),
        )
