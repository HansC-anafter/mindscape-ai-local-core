"""
Execution-chat-specific tool catalog.

Keeps the execution sidebar on a narrow, execution-relevant tool surface instead
of exposing the full MCP / workspace tool inventory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from backend.app.services.tool_list_service import (
    ToolInfo,
    ToolListService,
    get_tool_list_service,
)


ACTION_ONLY_GROUPS = {"execution_control", "execution_remote_control"}
ACTION_INTENT_KEYWORDS = (
    "continue",
    "resume",
    "proceed",
    "retry",
    "rerun",
    "resend",
    "approve",
    "go ahead",
    "繼續",
    "重送",
    "重跑",
    "重試",
    "重算",
    "批准",
    "同意",
)


@dataclass
class ExecutionChatToolDefinition:
    tool_id: str
    name: str
    description: str
    source: str
    category: str
    input_schema: Dict[str, Any]


class ExecutionChatToolCatalog:
    """Execution-chat scoped tool selector and prompt formatter."""

    TOOL_GROUPS: Dict[str, List[str]] = {
        "execution_inspection": [
            "workspace_get_execution",
            "workspace_get_execution_steps",
            "workspace_list_executions",
            "workspace_list_child_executions",
            "workspace_get_execution_remote_summary",
        ],
        "execution_control": [
            "workspace_continue_execution",
        ],
        "execution_remote_control": [
            "workspace_resend_remote_step",
        ],
    }

    def __init__(self, tool_list_service: Optional[ToolListService] = None):
        self.tool_list_service = tool_list_service or get_tool_list_service()

    def resolve_tools(
        self,
        *,
        workspace_id: Optional[str],
        requested_groups: Optional[Iterable[str]],
        user_message: str = "",
    ) -> List[ExecutionChatToolDefinition]:
        """Resolve tool groups into concrete tool definitions."""
        del workspace_id  # Reserved for future workspace-aware filtering.
        groups = list(requested_groups or [])
        if not groups:
            return []

        allow_action_groups = self._has_explicit_action_intent(user_message)
        resolved: List[ExecutionChatToolDefinition] = []
        seen: set[str] = set()

        for group in groups:
            if group in ACTION_ONLY_GROUPS and not allow_action_groups:
                continue

            for tool_id in self.TOOL_GROUPS.get(group, []):
                if tool_id in seen:
                    continue
                tool_info = self.tool_list_service.get_tool_by_id(tool_id)
                if not tool_info:
                    continue
                seen.add(tool_id)
                resolved.append(self._to_definition(tool_info))

        return resolved

    def format_tools_for_prompt(
        self, tools: Iterable[ExecutionChatToolDefinition]
    ) -> str:
        """Format tool definitions into a compact LLM-facing prompt block."""
        items = list(tools)
        if not items:
            return (
                "[AVAILABLE_TOOLS]\n"
                "No execution-specific tools are enabled for this playbook. "
                "Answer from the execution context only.\n"
                "[/AVAILABLE_TOOLS]"
            )

        parts = [
            "[AVAILABLE_TOOLS]",
            "Use tools when you need exact execution state or remote-step lineage data.",
            "When calling a tool, respond with JSON only:",
            '```json\n{"tool_call":{"tool_name":"workspace_get_execution","parameters":{"execution_id":"...","workspace_id":"..."}}}\n```',
            "",
        ]
        for tool in items:
            parts.append(f"- {tool.tool_id} ({tool.source}/{tool.category})")
            parts.append(f"  Description: {tool.description}")
            properties = tool.input_schema.get("properties", {})
            required = set(tool.input_schema.get("required", []))
            if properties:
                parts.append("  Parameters:")
                for param_name, param_schema in properties.items():
                    param_type = param_schema.get("type", "any")
                    desc = param_schema.get("description", "")
                    req = " required" if param_name in required else ""
                    parts.append(
                        f"    - {param_name}: {param_type}{req}. {desc}".rstrip()
                    )
            parts.append("")
        parts.append("[/AVAILABLE_TOOLS]")
        return "\n".join(parts)

    def _to_definition(self, tool_info: ToolInfo) -> ExecutionChatToolDefinition:
        input_schema = self._extract_input_schema(tool_info)
        return ExecutionChatToolDefinition(
            tool_id=tool_info.tool_id,
            name=tool_info.name,
            description=tool_info.description,
            source=tool_info.source,
            category=tool_info.category,
            input_schema=input_schema,
        )

    def _extract_input_schema(self, tool_info: ToolInfo) -> Dict[str, Any]:
        metadata = tool_info.metadata or {}
        builtin_tool = metadata.get("tool")
        if builtin_tool and hasattr(builtin_tool, "metadata"):
            schema = getattr(builtin_tool.metadata, "input_schema", None)
            if hasattr(schema, "model_dump"):
                return schema.model_dump()
            if isinstance(schema, dict):
                return schema

        tool_meta = metadata.get("tool_info")
        if isinstance(tool_meta, dict):
            input_schema = tool_meta.get("input_schema")
            if isinstance(input_schema, dict):
                return input_schema
            nested_meta = tool_meta.get("tool_info")
            if isinstance(nested_meta, dict):
                input_schema = nested_meta.get("input_schema")
                if isinstance(input_schema, dict):
                    return input_schema

        return {"type": "object", "properties": {}, "required": []}

    def _has_explicit_action_intent(self, user_message: str) -> bool:
        lowered = (user_message or "").strip().lower()
        if not lowered:
            return False
        return any(keyword in lowered for keyword in ACTION_INTENT_KEYWORDS)
