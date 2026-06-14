"""Apply selected pack role profile overlays to the core meeting roster."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.app.models.playbook import AgentDefinition

from .resolver import SelectedMeetingRoleProfile


def apply_meeting_role_profile_overlay(
    roster: Dict[str, AgentDefinition],
    selected_profile: SelectedMeetingRoleProfile,
) -> Dict[str, AgentDefinition]:
    """Return a new roster with allowed pack role overrides applied.

    Core slot identity is immutable: ``agent_id`` and ``role`` remain the base
    Meeting Engine semantics. Pack-specific identity is carried as metadata.
    """

    next_roster = dict(roster)
    profile_metadata = selected_profile.as_metadata()
    for slot_key, raw_overrides in selected_profile.slot_overrides.items():
        slot = str(slot_key or "").strip()
        if slot not in next_roster or not isinstance(raw_overrides, dict):
            continue

        base = next_roster[slot]
        system_prompt = _append_suffix(
            base.system_prompt,
            raw_overrides.get("system_prompt_suffix"),
        )
        tool_allowlist = _string_list(raw_overrides.get("tool_allowlist"))
        updates: Dict[str, Any] = {
            "system_prompt": system_prompt,
            "pack_role_name": _optional_string(raw_overrides.get("pack_role_name")),
            "meeting_role_profile_code": selected_profile.code,
            "meeting_lane_code": selected_profile.meeting_lane_code,
            "role_profile_metadata": {
                **profile_metadata,
                "slot": slot,
            },
        }
        if _optional_string(raw_overrides.get("agent_name")):
            updates["agent_name"] = _optional_string(raw_overrides.get("agent_name"))
        if tool_allowlist:
            updates["tools"] = tool_allowlist
        for field_name in (
            "responsibility_boundary",
            "communication_style",
            "capability_profile",
        ):
            value = _optional_string(raw_overrides.get(field_name))
            if value:
                updates[field_name] = value
        success_metrics = _string_list(raw_overrides.get("success_metrics"))
        if success_metrics:
            updates["success_metrics"] = success_metrics

        next_roster[slot] = base.model_copy(update=updates)
    return next_roster


def _append_suffix(base_prompt: str | None, suffix: Any) -> str | None:
    suffix_text = _optional_string(suffix)
    if not suffix_text:
        return base_prompt
    if not base_prompt:
        return suffix_text
    return f"{base_prompt}\n{suffix_text}"


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]
