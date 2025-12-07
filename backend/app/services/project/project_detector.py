"""
Project Detector service

Detects if a conversation message suggests creating a new Project.
Uses LLM to analyze user intent and determine if a project should be created.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from backend.app.models.project import ProjectSuggestion
from backend.app.models.workspace import Workspace
from backend.app.services.agent_runner import LLMProviderManager
from backend.app.shared.llm_provider_helper import (
    get_llm_provider_from_settings,
    create_llm_provider_manager,
    get_model_name_from_chat_model
)

logger = logging.getLogger(__name__)


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
            llm_provider: Optional LLM provider (will be created from settings if None)
        """
        self.llm_provider = llm_provider
        if llm_provider is None:
            llm_manager = create_llm_provider_manager()
            self.llm_provider = get_llm_provider_from_settings(llm_manager)

    async def detect(
        self,
        message: str,
        conversation_context: List[Dict[str, str]],
        workspace: Workspace
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

            # Build detection prompt
            prompt = f"""
Analyze the following conversation and determine if a new Project should be created.

Workspace type: {workspace.mode or 'general'}
User message: {message}

Recent conversation:
{context_str}

Determine:
1. mode: One of:
   - "quick_task": Simple query that can be handled quickly without a project
   - "micro_flow": Small task sequence that doesn't require full project setup
   - "project": Requires creating a dedicated project with its own sandbox and flow

2. If mode is "project", provide:
   - project_type: A descriptive project type identifier (e.g., "web_page", "book", "course", "campaign", "video_series", or any other appropriate type based on the context)
   - project_title: Suggested project title
   - flow_id: Suggested flow ID that matches the project type (e.g., "web_page_flow", "book_flow", or a generic "general_flow")
   - initial_spec_md: Initial specification in markdown format
   - confidence: Confidence score (0.0-1.0)

Note: project_type should be descriptive and appropriate for the work item. Common types include "web_page", "book", "course", "campaign", "video_series", but you can suggest other types if they better match the user's intent.

Respond in JSON format:
{{
    "mode": "quick_task|micro_flow|project",
    "project_type": "descriptive_project_type",
    "project_title": "Project title",
    "flow_id": "flow_identifier",
    "initial_spec_md": "Markdown specification",
    "confidence": 0.0-1.0
}}
"""

            # Call LLM
            messages = [
                {
                    "role": "system",
                    "content": "You are a project detection assistant. Analyze conversations to determine if a new project should be created. Return only valid JSON."
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
            suggestion = self._parse_response(result_text)
            return suggestion

        except Exception as e:
            logger.error(f"Project detection failed: {e}", exc_info=True)
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

    def _parse_response(self, response_text: str) -> Optional[ProjectSuggestion]:
        """Parse LLM response into ProjectSuggestion"""
        try:
            # Extract JSON from response (may contain markdown code blocks)
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

            if data.get("mode") != "project":
                return None

            return ProjectSuggestion(
                mode=data.get("mode", "quick_task"),
                project_type=data.get("project_type"),
                project_title=data.get("project_title"),
                flow_id=data.get("flow_id"),
                initial_spec_md=data.get("initial_spec_md"),
                confidence=data.get("confidence", 0.0)
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse project detection response: {e}")
            return None

