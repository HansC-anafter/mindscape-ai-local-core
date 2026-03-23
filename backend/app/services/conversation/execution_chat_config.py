"""
Execution-chat configuration resolver.

Normalizes the local-core-specific execution-chat overlay into one stable shape
while preserving compatibility with legacy top-level PlaybookMetadata fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from backend.app.models.playbook import PlaybookMetadata


ExecutionChatMode = Literal["discussion", "agent"]


@dataclass(frozen=True)
class ExecutionChatConfig:
    """Normalized execution-chat configuration."""

    enabled: bool = False
    mode: ExecutionChatMode = "discussion"
    tool_groups: List[str] = field(default_factory=list)
    max_tool_iterations: int = 5
    discussion_agent: Optional[str] = None
    source: str = "legacy"


def resolve_execution_chat_config(
    playbook_metadata: Optional[PlaybookMetadata],
) -> ExecutionChatConfig:
    """Resolve execution-chat config from x_platform with legacy fallback."""
    if not playbook_metadata:
        return ExecutionChatConfig()

    overlay = _extract_execution_chat_overlay(playbook_metadata.x_platform)

    enabled = _resolve_enabled(playbook_metadata, overlay)
    mode = _resolve_mode(playbook_metadata, overlay)
    tool_groups = _resolve_tool_groups(playbook_metadata, overlay)
    max_tool_iterations = _resolve_max_iterations(playbook_metadata, overlay)
    discussion_agent = _resolve_discussion_agent(playbook_metadata, overlay)

    if overlay:
        source = "x_platform.local_core.execution_chat"
    elif _has_legacy_execution_chat_fields(playbook_metadata):
        source = "legacy"
    else:
        source = "default"

    return ExecutionChatConfig(
        enabled=enabled,
        mode=mode,
        tool_groups=tool_groups,
        max_tool_iterations=max_tool_iterations,
        discussion_agent=discussion_agent,
        source=source,
    )


def build_execution_chat_payload(
    playbook_metadata: Optional[PlaybookMetadata],
) -> Dict[str, Any]:
    """Project execution-chat config into a response-friendly payload."""
    config = resolve_execution_chat_config(playbook_metadata)
    return {
        "supports_execution_chat": config.enabled,
        "execution_chat_mode": config.mode,
        "execution_chat_tool_groups": list(config.tool_groups),
        "execution_chat_max_tool_iterations": config.max_tool_iterations,
        "discussion_agent": config.discussion_agent,
    }


def _extract_execution_chat_overlay(
    x_platform: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(x_platform, dict):
        return {}

    local_core = x_platform.get("local_core")
    if not isinstance(local_core, dict):
        return {}

    execution_chat = local_core.get("execution_chat")
    if not isinstance(execution_chat, dict):
        return {}

    return execution_chat


def _resolve_enabled(
    playbook_metadata: PlaybookMetadata,
    overlay: Dict[str, Any],
) -> bool:
    if "enabled" in overlay:
        return bool(overlay.get("enabled"))
    if overlay:
        return True
    return bool(playbook_metadata.supports_execution_chat)


def _resolve_mode(
    playbook_metadata: PlaybookMetadata,
    overlay: Dict[str, Any],
) -> ExecutionChatMode:
    mode = overlay.get("mode") if isinstance(overlay.get("mode"), str) else None
    if mode in {"discussion", "agent"}:
        return mode

    legacy_mode = getattr(playbook_metadata, "execution_chat_mode", "discussion")
    if legacy_mode in {"discussion", "agent"}:
        return legacy_mode

    return "discussion"


def _resolve_tool_groups(
    playbook_metadata: PlaybookMetadata,
    overlay: Dict[str, Any],
) -> List[str]:
    groups = overlay.get("tool_groups")
    if isinstance(groups, list):
        return [str(group) for group in groups if isinstance(group, str) and group]

    legacy_groups = getattr(playbook_metadata, "execution_chat_tool_groups", [])
    if isinstance(legacy_groups, (list, tuple, set)):
        return [
            str(group)
            for group in legacy_groups
            if isinstance(group, str) and group
        ]

    return []


def _resolve_max_iterations(
    playbook_metadata: PlaybookMetadata,
    overlay: Dict[str, Any],
) -> int:
    raw_value = overlay.get("max_tool_iterations")
    if raw_value is None:
        raw_value = getattr(playbook_metadata, "execution_chat_max_tool_iterations", 5)

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 5

    return max(1, min(value, 20))


def _resolve_discussion_agent(
    playbook_metadata: PlaybookMetadata,
    overlay: Dict[str, Any],
) -> Optional[str]:
    agent = overlay.get("discussion_agent")
    if isinstance(agent, str) and agent.strip():
        return agent.strip()

    legacy_agent = getattr(playbook_metadata, "discussion_agent", None)
    if isinstance(legacy_agent, str) and legacy_agent.strip():
        return legacy_agent.strip()

    return None


def _has_legacy_execution_chat_fields(playbook_metadata: PlaybookMetadata) -> bool:
    return bool(
        playbook_metadata.supports_execution_chat
        or playbook_metadata.execution_chat_tool_groups
        or playbook_metadata.discussion_agent
        or playbook_metadata.execution_chat_mode != "discussion"
        or playbook_metadata.execution_chat_max_tool_iterations != 5
    )
