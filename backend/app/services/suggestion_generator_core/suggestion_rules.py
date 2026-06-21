"""Pure suggestion rule helpers for the workbench suggestion generator."""

from typing import Any, Dict, List


def generate_file_suggestions(
    context: Dict[str, Any],
    installed_packs: List[Dict[str, Any]],
    available_playbooks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate suggestions based on the most recent file."""
    suggestions: List[Dict[str, Any]] = []
    _ = installed_packs

    recent_file = context.get("recent_file", {})
    file_name = recent_file.get("name", "")

    grant_playbook = next(
        (
            pb
            for pb in available_playbooks
            if "grant" in pb["playbook_code"].lower()
            or "government" in pb["playbook_code"].lower()
        ),
        None,
    )
    if grant_playbook:
        suggestions.append(
            {
                "title": f"Process {file_name}",
                "description": (
                    f"Use {grant_playbook['name']} to process this document"
                ),
                "action": "execute_playbook",
                "params": {
                    "playbook_code": grant_playbook["playbook_code"],
                    "file_name": file_name,
                },
                "cta_label": "Process Document",
                "priority": "high",
                "side_effect_level": "readonly",
            }
        )

    proposal_playbook = next(
        (
            pb
            for pb in available_playbooks
            if "proposal" in pb["playbook_code"].lower()
            or "major" in pb["playbook_code"].lower()
        ),
        None,
    )
    if proposal_playbook and file_name.lower().endswith((".pdf", ".docx", ".doc")):
        suggestions.append(
            {
                "title": f"Analyze {file_name}",
                "description": (
                    f"Extract structure and create proposal from {file_name}"
                ),
                "action": "execute_playbook",
                "params": {
                    "playbook_code": proposal_playbook["playbook_code"],
                    "file_name": file_name,
                },
                "cta_label": "Create Proposal",
                "priority": "high",
                "side_effect_level": "soft_write",
            }
        )

    if file_name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
        suggestions.append(
            {
                "title": f"Extract text from {file_name}",
                "description": "Use OCR to extract text from scanned document",
                "action": "use_tool",
                "params": {
                    "tool": "core_files.extract_text",
                    "file_path": file_name,
                },
                "cta_label": "Extract Text",
                "priority": "medium",
                "side_effect_level": "readonly",
            }
        )

    return suggestions


def generate_intent_suggestions(
    context: Dict[str, Any],
    installed_packs: List[Dict[str, Any]],
    has_intents: bool,
    i18n: Any,
) -> List[Dict[str, Any]]:
    """Generate suggestions based on detected intents."""
    suggestions: List[Dict[str, Any]] = []

    if not has_intents:
        suggestions.append(
            {
                "title": i18n.t(
                    "conversation_orchestrator",
                    "suggestion.create_intent_card_title",
                ),
                "description": i18n.t(
                    "conversation_orchestrator",
                    "suggestion.create_intent_card_description",
                ),
                "action": "create_intent",
                "params": {},
                "cta_label": i18n.t(
                    "conversation_orchestrator",
                    "suggestion.create_intent_card_cta",
                ),
                "priority": "medium",
                "side_effect_level": "soft_write",
            }
        )
    else:
        daily_planning_pack = next(
            (p for p in installed_packs if p["pack_id"] == "daily_planning"),
            None,
        )
        if daily_planning_pack and daily_planning_pack.get("tools_configured"):
            suggestions.append(
                {
                    "title": i18n.t(
                        "conversation_orchestrator",
                        "suggestion.organize_tasks_title",
                    ),
                    "description": i18n.t(
                        "conversation_orchestrator",
                        "suggestion.organize_tasks_description",
                    ),
                    "action": "use_tool",
                    "params": {
                        "tool": "daily_planning.extract_tasks",
                        "workspace_id": context.get("workspace_id"),
                    },
                    "cta_label": i18n.t(
                        "conversation_orchestrator",
                        "suggestion.organize_tasks_cta",
                    ),
                    "priority": "high",
                    "side_effect_level": "soft_write",
                }
            )

    return suggestions


def check_playbook_tools_available(
    playbook: Dict[str, Any],
    installed_packs: List[Dict[str, Any]],
    registry: Any,
) -> bool:
    """Check if all required tools for a playbook are available."""
    tool_deps = playbook.get("tool_dependencies", [])
    if not tool_deps:
        return True

    for tool_dep in tool_deps:
        tool_name = tool_dep.split(".")[-1] if "." in tool_dep else tool_dep
        capability_code = tool_dep.split(".")[0] if "." in tool_dep else None

        tool_available = any(
            any(t.get("name") == tool_name for t in pack.get("tools", []))
            for pack in installed_packs
            if not capability_code or pack["pack_id"] == capability_code
        )

        if not tool_available:
            registry_tool = registry.get_tool(tool_dep)
            tool_available = registry_tool is not None

        if not tool_available:
            return False

    return True


def build_content_summary(
    timeline_items: List[Dict[str, Any]],
    assistant_messages: List[Dict[str, Any]],
    workspace_focus: str,
) -> str:
    """Build a bounded content summary for LLM analysis."""
    parts: List[str] = []

    if workspace_focus:
        parts.append(f"Workspace Focus: {workspace_focus[:200]}")

    if timeline_items:
        parts.append(f"\nTimeline Items ({len(timeline_items)}):")
        for item in timeline_items[:5]:
            item_type = item.get("type", "unknown")
            title = item.get("title", "")[:100] if item.get("title") else "No title"
            summary = item.get("summary", "")[:150] if item.get("summary") else ""
            parts.append(f"  - {item_type}: {title}")
            if summary:
                parts.append(f"    Summary: {summary}")

    if assistant_messages:
        parts.append(f"\nRecent Assistant Messages ({len(assistant_messages)}):")
        for msg in assistant_messages[:3]:
            message_text = msg.get("message", "")[:300]
            if message_text:
                parts.append(f"  - {message_text}")

    return "\n".join(parts) if parts else "No content available"


def generate_pack_suggestions(
    context: Dict[str, Any],
    installed_packs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate suggestions based on installed capability packs."""
    suggestions: List[Dict[str, Any]] = []
    workspace_focus = context.get("workspace_focus")

    for pack in installed_packs:
        if not pack.get("tools_configured"):
            continue

        pack_id = pack["pack_id"]

        if pack_id == "content_drafting" and workspace_focus:
            suggestions.append(
                {
                    "title": "Draft Content",
                    "description": f"Create content draft for: {workspace_focus[:50]}",
                    "action": "use_tool",
                    "params": {
                        "tool": "content_drafting.generate",
                        "topic": workspace_focus,
                    },
                    "cta_label": "Draft Content",
                    "priority": "medium",
                    "side_effect_level": pack.get("side_effect_level", "readonly"),
                }
            )
        elif pack_id == "research" and workspace_focus:
            suggestions.append(
                {
                    "title": "Research Topic",
                    "description": f"Research: {workspace_focus[:50]}",
                    "action": "use_tool",
                    "params": {
                        "tool": "research.search",
                        "query": workspace_focus,
                    },
                    "cta_label": "Research",
                    "priority": "medium",
                    "side_effect_level": "readonly",
                }
            )
        elif pack_id == "semantic_seeds":
            if workspace_focus or context.get("recent_file"):
                suggestions.append(
                    {
                        "title": "Extract Intent Seeds",
                        "description": "Extract themes and intents from your content",
                        "action": "use_tool",
                        "params": {
                            "tool": "semantic_seeds.extract_seeds",
                            "workspace_id": context.get("workspace_id"),
                        },
                        "cta_label": "Extract Seeds",
                        "priority": "medium",
                        "side_effect_level": "readonly",
                    }
                )

    return suggestions


def generate_fallback_suggestions(i18n: Any) -> List[Dict[str, Any]]:
    """Generate fallback suggestions when no specific suggestions are available."""
    return [
        {
            "title": i18n.t(
                "conversation_orchestrator",
                "suggestion.start_conversation_title",
            ),
            "description": i18n.t(
                "conversation_orchestrator",
                "suggestion.start_conversation_description",
            ),
            "action": "start_chat",
            "params": {},
            "cta_label": i18n.t(
                "conversation_orchestrator",
                "suggestion.start_conversation_cta",
            ),
            "priority": "low",
            "side_effect_level": "readonly",
        },
        {
            "title": i18n.t(
                "conversation_orchestrator",
                "suggestion.upload_file_title",
            ),
            "description": i18n.t(
                "conversation_orchestrator",
                "suggestion.upload_file_description",
            ),
            "action": "upload_file",
            "params": {},
            "cta_label": i18n.t(
                "conversation_orchestrator",
                "suggestion.upload_file_cta",
            ),
            "priority": "low",
            "side_effect_level": "readonly",
        },
    ]


def priority_score(priority: str) -> int:
    """Convert priority to a numeric score for sorting."""
    scores = {"high": 3, "medium": 2, "low": 1}
    return scores.get(priority, 0)
