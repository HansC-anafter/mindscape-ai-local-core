"""
External Agent Tools Wrapper

Wraps functional tools from backend.app.tools.external_agent_tools into MindscapeTool classes.
"""

import logging
from typing import Dict, Any, List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolInputSchema,
    ToolCategory,
)
from backend.app.tools.external_agent_tools import (
    execute_agent,
    list_agents,
    check_agent,
)

logger = logging.getLogger(__name__)


class ExternalAgentExecuteTool(MindscapeTool):
    """Execute a task using a registered external agent"""

    def __init__(self):
        metadata = ToolMetadata(
            name="external_agent_execute",
            description="Execute a task using a registered external agent",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "agent": {
                        "type": "string",
                        "description": "Agent name (e.g., 'gemini_cli', 'openclaw')",
                    },
                    "task": {
                        "type": "string",
                        "description": "The task description for the agent to execute",
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of allowed tools (optional)",
                    },
                    "denied_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of denied tools (optional)",
                    },
                    "max_duration": {
                        "type": "integer",
                        "default": 300,
                        "description": "Maximum execution time in seconds",
                    },
                    "context": {
                        "type": "object",
                        "description": "Mindscape execution context (workspace_id, etc.)",
                    },
                },
                required=["agent", "task"],
            ),
            category=ToolCategory.AI,
            source_type="builtin",
            provider="core",
            danger_level="high",
        )
        super().__init__(metadata)

    async def execute(
        self,
        agent: str,
        task: str,
        allowed_tools: Optional[List[str]] = None,
        denied_tools: Optional[List[str]] = None,
        max_duration: int = 300,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute agent"""
        return await execute_agent(
            agent=agent,
            task=task,
            allowed_tools=allowed_tools,
            denied_tools=denied_tools,
            max_duration=max_duration,
            context=context,
        )


class ExternalAgentListTool(MindscapeTool):
    """List all registered external agents"""

    def __init__(self):
        metadata = ToolMetadata(
            name="external_agent_list",
            description="List all registered external agents",
            input_schema=ToolInputSchema(type="object", properties={}, required=[]),
            category=ToolCategory.Data,
            source_type="builtin",
            provider="core",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(self) -> Dict[str, Any]:
        """List agents"""
        return await list_agents()


class ExternalAgentCheckTool(MindscapeTool):
    """Check if a specific agent is available"""

    def __init__(self):
        metadata = ToolMetadata(
            name="external_agent_check",
            description="Check if a specific agent is available",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "agent": {"type": "string", "description": "Agent name to check"}
                },
                required=["agent"],
            ),
            category=ToolCategory.Data,
            source_type="builtin",
            provider="core",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(self, agent: str) -> Dict[str, Any]:
        """Check agent"""
        return await check_agent(agent)
