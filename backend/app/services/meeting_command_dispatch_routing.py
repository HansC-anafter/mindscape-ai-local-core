"""Routing and payload helpers for meeting command dispatch."""

from __future__ import annotations

import os
from typing import Any

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
)


def meeting_orchestration_timeout_seconds(
    canonical: MeetingCommandEnvelope | None = None,
) -> float:
    metadata = canonical.metadata if canonical is not None else {}
    raw_value = (
        metadata.get("meeting_orchestration_timeout_seconds")
        or metadata.get("orchestration_timeout_seconds")
        or os.environ.get("MEETING_COMMAND_ORCHESTRATION_TIMEOUT_SECONDS", "120")
    )
    raw_cap = os.environ.get("MEETING_COMMAND_ORCHESTRATION_MAX_TIMEOUT_SECONDS", "3600")
    try:
        timeout_cap = max(5.0, float(raw_cap))
    except (TypeError, ValueError):
        timeout_cap = 3600.0
    try:
        return min(timeout_cap, max(5.0, float(raw_value)))
    except (TypeError, ValueError):
        return 120.0


def command_instruction(canonical: MeetingCommandEnvelope) -> str:
    if isinstance(canonical.intent_text, str) and canonical.intent_text.strip():
        return canonical.intent_text.strip()
    raw_intent = canonical.metadata.get("raw_intent_text")
    if isinstance(raw_intent, str) and raw_intent.strip():
        return raw_intent.strip()
    return canonical.intent_text


def requested_affordance_verb(canonical: MeetingCommandEnvelope) -> str | None:
    requested = canonical.requested_action
    if requested is None:
        return None
    if requested.affordance_verb:
        return requested.affordance_verb
    if requested.verb and requested.verb not in {"execute_playbook", "command"}:
        return requested.verb
    return None


def explicit_direct_override(canonical: MeetingCommandEnvelope) -> bool:
    return canonical.metadata.get("explicit_override") is True


def _truthy_flag(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _metadata_action_value(canonical: MeetingCommandEnvelope, key: str) -> Any:
    metadata = canonical.metadata or {}
    action_parameters = metadata.get("action_parameters")
    if not isinstance(action_parameters, dict):
        action_parameters = {}
    if key in metadata:
        return metadata.get(key)
    return action_parameters.get(key)


def _command_active_capability_code(canonical: MeetingCommandEnvelope) -> str | None:
    metadata = canonical.metadata or {}
    action_parameters = metadata.get("action_parameters")
    if not isinstance(action_parameters, dict):
        action_parameters = {}
    for value in (
        metadata.get("active_capability_code"),
        metadata.get("active_pack_code"),
        action_parameters.get("active_capability_code"),
        action_parameters.get("active_pack_code"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def _has_selected_guidance(canonical: MeetingCommandEnvelope) -> bool:
    metadata = canonical.metadata or {}
    action_parameters = metadata.get("action_parameters")
    if not isinstance(action_parameters, dict):
        action_parameters = {}
    return any(
        value not in (None, "", [], {})
        for value in (
            metadata.get("selected_guidance_id"),
            metadata.get("selected_guidance_ids"),
            metadata.get("selected_guidance_metadata"),
            metadata.get("selected_guidance_cards"),
            action_parameters.get("selected_guidance_id"),
            action_parameters.get("selected_guidance_ids"),
            action_parameters.get("selected_guidance_metadata"),
            action_parameters.get("selected_guidance_cards"),
        )
    )


def metadata_action_parameters(canonical: MeetingCommandEnvelope) -> dict:
    action_parameters = canonical.metadata.get("action_parameters")
    return action_parameters if isinstance(action_parameters, dict) else {}


def _has_action_entries(canonical: MeetingCommandEnvelope) -> bool:
    action_parameters = metadata_action_parameters(canonical)
    entries = action_parameters.get("object_action_entries")
    return isinstance(entries, list) and bool(entries)


def _is_explicit_playbook_route(canonical: MeetingCommandEnvelope) -> bool:
    return (
        canonical.metadata.get("dispatch_mode") == "route_playbook"
        and explicit_direct_override(canonical)
        and canonical.requested_action is not None
        and bool(canonical.requested_action.playbook_code)
    )


def _is_motion_practice_playbook_command(canonical: MeetingCommandEnvelope) -> bool:
    return _is_explicit_playbook_route(canonical) and (
        _truthy_flag(_metadata_action_value(canonical, "motion_practice_launch"))
        or _truthy_flag(_metadata_action_value(canonical, "motion_practice_command"))
    )


def should_route_meeting_orchestration(canonical: MeetingCommandEnvelope) -> bool:
    dispatch_mode = canonical.metadata.get("dispatch_mode")
    if _is_motion_practice_playbook_command(canonical):
        return False
    if _truthy_flag(_metadata_action_value(canonical, "force_meeting_orchestration")):
        return True
    if _truthy_flag(_metadata_action_value(canonical, "forceMeetingOrchestration")):
        return True
    if dispatch_mode == "route_meeting_orchestration":
        return True
    if (
        dispatch_mode in {"route_object_action", "route_playbook"}
        and explicit_direct_override(canonical)
    ):
        return False
    if canonical.context_objects:
        return True
    if canonical.meeting_mentions:
        return True
    if canonical.requested_action and canonical.requested_action.playbook_code:
        return True
    if canonical.metadata.get("selected_pack_tool_id"):
        return True
    if _has_selected_guidance(canonical):
        return True
    if _has_action_entries(canonical):
        return True
    return False


def should_route_object_action(canonical: MeetingCommandEnvelope) -> bool:
    return (
        canonical.metadata.get("dispatch_mode") == "route_object_action"
        and explicit_direct_override(canonical)
        and len(canonical.context_objects) >= 2
        and not (canonical.requested_action and canonical.requested_action.playbook_code)
    )


def should_route_client_action(canonical: MeetingCommandEnvelope) -> bool:
    requested = canonical.requested_action
    return (
        canonical.metadata.get("dispatch_mode") == "route_client_action"
        and explicit_direct_override(canonical)
        and requested is not None
        and requested.verb == "client_action"
        and bool(requested.pack_code)
        and bool(requested.affordance_verb)
        and isinstance(requested.parameters.get("client_action"), dict)
    )


def should_route_playbook(canonical: MeetingCommandEnvelope) -> bool:
    return _is_explicit_playbook_route(canonical)


def should_route_chat(canonical: MeetingCommandEnvelope) -> bool:
    return (
        canonical.metadata.get("dispatch_mode") == "route_chat"
        and not should_route_meeting_orchestration(canonical)
        and not (canonical.requested_action and canonical.requested_action.playbook_code)
    )


def command_context_objects(canonical: MeetingCommandEnvelope) -> list[dict]:
    return [entry.model_dump(exclude_none=True) for entry in canonical.context_objects]
