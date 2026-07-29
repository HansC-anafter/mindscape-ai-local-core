"""Resolve pack-declared voice intents into bounded AOL client actions."""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingRequestedAction,
)
from backend.app.models.meeting_voice_context import MeetingVoiceCommandContext
from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)


CLIENT_ACTION_SCHEMA_VERSION = "aol.client_action.v1"
MAX_VOICE_INTENTS = 32
MAX_MATCH_PHRASES = 32
MAX_PAYLOAD_KEYS = 64


@dataclass(frozen=True)
class VoiceClientActionResolution:
    pack_code: str
    intent_code: str
    action_code: str
    requires_confirmation: bool
    payload: dict[str, Any]


def _normalized_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _active_pack_code(session: Any) -> str:
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, Mapping):
        return ""
    aol = metadata.get("aol")
    nested = aol if isinstance(aol, Mapping) else {}
    for value in (
        metadata.get("active_capability_code"),
        metadata.get("active_pack_code"),
        metadata.get("coach_pack"),
        nested.get("active_capability_code"),
        nested.get("active_pack_code"),
    ):
        cleaned = _clean_string(value)
        if cleaned:
            return cleaned
    return ""


def _read_installed_manifest(manifest_path: Path) -> Mapping[str, Any]:
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return manifest if isinstance(manifest, Mapping) else {}


def _manifest_for_pack(pack_code: str, registry: Any | None) -> Mapping[str, Any]:
    if not pack_code:
        return {}
    if registry is not None:
        capability = registry.get_capability(pack_code)
        if not isinstance(capability, Mapping):
            return {}
        manifest = capability.get("manifest")
        return manifest if isinstance(manifest, Mapping) else {}
    paths = PlannerContractManifestRegistry().capability_manifest_paths(pack_code)
    for manifest_path in paths:
        if manifest_path.exists():
            return _read_installed_manifest(manifest_path)
    return {}


def _matches_intent(transcript: str, match: Mapping[str, Any]) -> bool:
    normalized_transcript = _normalized_text(transcript)
    if not normalized_transcript:
        return False
    phrases = match.get("phrases")
    if not isinstance(phrases, list):
        return False
    normalized_phrases = [
        normalized
        for value in phrases[:MAX_MATCH_PHRASES]
        if (normalized := _normalized_text(value))
    ]
    mode = _clean_string(match.get("mode")) or "contains"
    if mode == "exact":
        return normalized_transcript in normalized_phrases
    if mode == "contains":
        return any(phrase in normalized_transcript for phrase in normalized_phrases)
    return False


def resolve_voice_client_action(
    *,
    transcript: str,
    session: Any,
    registry: Any | None = None,
) -> VoiceClientActionResolution | None:
    pack_code = _active_pack_code(session)
    manifest = _manifest_for_pack(pack_code, registry)
    contract = manifest.get("aol_client_interactions")
    if not isinstance(contract, Mapping):
        return None
    intents = contract.get("voice_intents")
    if not isinstance(intents, list):
        return None
    for raw_intent in intents[:MAX_VOICE_INTENTS]:
        if not isinstance(raw_intent, Mapping):
            continue
        match = raw_intent.get("match")
        action = raw_intent.get("action")
        if not isinstance(match, Mapping) or not isinstance(action, Mapping):
            continue
        if not _matches_intent(transcript, match):
            continue
        intent_code = _clean_string(raw_intent.get("code"))
        action_code = _clean_string(action.get("code"))
        payload = action.get("payload")
        if not intent_code or not action_code or not isinstance(payload, Mapping):
            continue
        if len(payload) > MAX_PAYLOAD_KEYS:
            continue
        return VoiceClientActionResolution(
            pack_code=pack_code,
            intent_code=intent_code,
            action_code=action_code,
            requires_confirmation=bool(action.get("requires_confirmation")),
            payload=copy.deepcopy(dict(payload)),
        )
    return None


def build_voice_command_envelope(
    *,
    workspace_id: str,
    meeting_id: str,
    origin_surface: str,
    transcript: str,
    metadata: Mapping[str, Any],
    context_objects: list[Any],
    resolution: VoiceClientActionResolution | None,
    command_context: MeetingVoiceCommandContext | None = None,
) -> MeetingCommandEnvelope:
    context = command_context or MeetingVoiceCommandContext(
        context_objects=context_objects,
    )
    context_metadata = copy.deepcopy(context.metadata)
    context_metadata.update(dict(metadata))
    context_metadata["raw_intent_text"] = transcript
    action_parameters = context_metadata.get("action_parameters")
    if isinstance(action_parameters, Mapping):
        normalized_action_parameters = copy.deepcopy(dict(action_parameters))
        normalized_action_parameters["meeting_command"] = transcript
        context_metadata["action_parameters"] = normalized_action_parameters
    requested_action = context.requested_action.model_copy(deep=True) \
        if context.requested_action is not None else None
    if requested_action is not None:
        requested_action.parameters["instruction"] = transcript
        requested_action.parameters["message"] = transcript
        if "meeting_command" in requested_action.parameters:
            requested_action.parameters["meeting_command"] = transcript

    if resolution is None:
        return MeetingCommandEnvelope(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            origin_surface=origin_surface,
            actor="user",
            intent_text=transcript,
            context_objects=context.context_objects,
            requested_action=requested_action,
            expected_outputs=context.expected_outputs,
            write_mode=context.write_mode,
            thread_id=context.thread_id,
            meeting_mentions=context.meeting_mentions,
            metadata=context_metadata,
        )
    if requested_action is not None:
        return MeetingCommandEnvelope(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            origin_surface=origin_surface,
            actor="user",
            intent_text=transcript,
            context_objects=context.context_objects,
            requested_action=requested_action,
            expected_outputs=context.expected_outputs,
            write_mode=context.write_mode,
            thread_id=context.thread_id,
            meeting_mentions=context.meeting_mentions,
            metadata=context_metadata,
        )
    client_action = {
        "schema_version": CLIENT_ACTION_SCHEMA_VERSION,
        "pack_code": resolution.pack_code,
        "intent_code": resolution.intent_code,
        "action_code": resolution.action_code,
        "requires_confirmation": resolution.requires_confirmation,
        "payload": resolution.payload,
    }
    return MeetingCommandEnvelope(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        origin_surface=origin_surface,
        actor="user",
        intent_text=transcript,
        context_objects=context.context_objects,
        requested_action=MeetingRequestedAction(
            verb="client_action",
            pack_code=resolution.pack_code,
            affordance_verb=resolution.action_code,
            write_mode="recommendation_only",
            parameters={"client_action": client_action},
        ),
        expected_outputs=context.expected_outputs,
        write_mode=context.write_mode,
        thread_id=context.thread_id,
        meeting_mentions=context.meeting_mentions,
        metadata={
            **context_metadata,
            "dispatch_mode": "route_client_action",
            "explicit_override": True,
            "active_pack_code": resolution.pack_code,
            "client_action": client_action,
        },
    )


__all__ = [
    "CLIENT_ACTION_SCHEMA_VERSION",
    "VoiceClientActionResolution",
    "build_voice_command_envelope",
    "resolve_voice_client_action",
]
