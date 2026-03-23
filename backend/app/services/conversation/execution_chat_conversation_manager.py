"""
Execution chat conversation manager.

Provides the minimal interface expected by ToolExecutionLoop without reusing the
playbook-SOP-specific prompt framing from PlaybookConversationManager.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.services.playbook.conversation_manager import (
    PlaybookConversationManager,
)


class ExecutionChatConversationManager(PlaybookConversationManager):
    """Conversation manager specialized for execution-scoped agent chat."""

    def __init__(
        self,
        *,
        execution_id: str,
        workspace_id: str,
        execution_context: str,
        tool_prompt: str,
        discussion_agent: Optional[str],
        target_language: str,
        store: Any = None,
        project_id: Optional[str] = None,
    ):
        self.playbook = None
        self.profile = None
        self.project = None
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.auto_execute = False
        self.store = store
        self.locale = target_language
        self.target_language = target_language
        self.conversation_history = []
        self.extracted_data: Dict[str, Any] = {}
        self.current_step = 0
        self.variant = None
        self.skip_steps = []
        self.custom_checklist = []
        self.cached_tools_str = None
        self.execution_id = execution_id
        self.execution_context = execution_context
        self.tool_prompt = tool_prompt.strip()
        self.discussion_agent = discussion_agent or "assistant"

    async def build_system_prompt(self) -> str:
        prompt_parts = [
            f"You are {self.discussion_agent}, the execution-side assistant for a single playbook run.",
            "",
            "## Scope",
            f"- Focus only on execution_id={self.execution_id}.",
            "- Do not invent execution state. Use tools when exact status, steps, or remote lineage matter.",
            "- Do not claim an action happened unless the tool result confirms it.",
            "- If no tool is available for a requested action, explain that limitation directly.",
            "",
            "## Response Contract",
            f"- Reply in {self.target_language}.",
            "- Prefer concise factual answers.",
            "- When a tool is needed, output valid JSON tool-call payloads only.",
            "",
            "## Execution Context",
            self.execution_context,
            "",
            self.tool_prompt,
        ]
        return "\n".join(part for part in prompt_parts if part is not None)

    def extract_structured_output(self, assistant_message: str):
        """Execution chat agent replies do not use STRUCTURED_OUTPUT contracts."""
        return None
