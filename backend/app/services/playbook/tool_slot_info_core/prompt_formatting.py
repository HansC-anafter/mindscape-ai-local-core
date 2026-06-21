"""Prompt formatting helpers for tool slot information."""

from __future__ import annotations

from typing import Dict, List

from backend.app.services.playbook.tool_slot_info_core.types import ToolSlotInfo


def format_slot_info_for_prompt(
    slot_info_map: Dict[str, ToolSlotInfo],
    include_policy: bool = True,
    include_mapped_tool: bool = True,
    include_relevance_score: bool = False,
) -> str:
    """Format slot information for prompt injection."""
    if not slot_info_map:
        return ""

    lines = ["[AVAILABLE_TOOL_SLOTS]"]
    lines.append(
        "The following tool slots are available for this Playbook. Use slot names instead of concrete tool_id."
    )
    lines.append("")

    playbook_slots = {
        slot: info for slot, info in slot_info_map.items() if info.source == "playbook"
    }
    workspace_slots = {
        slot: info for slot, info in slot_info_map.items() if info.source == "workspace"
    }
    project_slots = {
        slot: info for slot, info in slot_info_map.items() if info.source == "project"
    }
    capability_slots = {
        slot: info for slot, info in slot_info_map.items() if info.source == "capability"
    }

    if playbook_slots:
        lines.append("## Priority Use (From Playbook Definition):")
        for slot, info in sorted(playbook_slots.items(), key=_slot_sort_key(include_relevance_score)):
            lines.extend(
                _format_slot_info(
                    slot,
                    info,
                    include_policy,
                    include_mapped_tool,
                    include_relevance_score,
                )
            )
        lines.append("")

    if project_slots:
        lines.append("## Project Level Mapping:")
        for slot, info in sorted(project_slots.items(), key=_slot_sort_key(include_relevance_score)):
            lines.extend(
                _format_slot_info(
                    slot,
                    info,
                    include_policy,
                    include_mapped_tool,
                    include_relevance_score,
                )
            )
        lines.append("")

    if workspace_slots:
        lines.append("## Workspace Level Mapping:")
        for slot, info in sorted(workspace_slots.items(), key=_slot_sort_key(include_relevance_score)):
            lines.extend(
                _format_slot_info(
                    slot,
                    info,
                    include_policy,
                    include_mapped_tool,
                    include_relevance_score,
                )
            )
        lines.append("")

    if capability_slots:
        lines.append("## Installed Capabilities:")
        for slot, info in sorted(capability_slots.items(), key=_slot_sort_key(include_relevance_score)):
            lines.extend(
                _format_slot_info(
                    slot,
                    info,
                    include_policy,
                    include_mapped_tool,
                    include_relevance_score,
                )
            )
        lines.append("")

    lines.append("[/AVAILABLE_TOOL_SLOTS]")
    return "\n".join(lines)


def _slot_sort_key(include_relevance_score: bool):
    def sort_key(item):
        _, info = item
        relevance_score = (
            info.relevance_score
            if (include_relevance_score and info.relevance_score is not None)
            else 0.0
        )
        return (-info.priority, -relevance_score)

    return sort_key


def _format_slot_info(
    slot: str,
    info: ToolSlotInfo,
    include_policy: bool,
    include_mapped_tool: bool,
    include_relevance_score: bool = False,
) -> List[str]:
    lines = [f"- **{slot}**"]

    if include_relevance_score and info.relevance_score is not None:
        score_str = f"{info.relevance_score:.2f}"
        lines.append(f"  - Relevance: {score_str}")

    if info.description:
        lines.append(f"  - Description: {info.description}")

    if include_policy and info.policy:
        policy_parts = [
            f"risk={info.policy.risk_level}",
            f"env={info.policy.env}",
        ]
        if info.policy.requires_preview:
            policy_parts.append("requires_preview=true")
        lines.append(f"  - Policy: {', '.join(policy_parts)}")

    if include_mapped_tool and info.mapped_tool_id:
        lines.append(f"  - Mapped to: {info.mapped_tool_id}")

    return lines
