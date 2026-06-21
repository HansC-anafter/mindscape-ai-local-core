"""Pure helpers for AOL meeting orchestration handoff construction."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.meeting_command import MeetingCommandRecord
from backend.app.models.object_runtime import ObjectRef


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _clean_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _ref_key(ref: ObjectRef) -> str:
    return ref.uri or f"{ref.owner_pack}:{ref.object_kind}:{ref.object_id}"


def _append_unique_ref(refs: List[ObjectRef], ref: ObjectRef) -> None:
    key = _ref_key(ref)
    if key and all(_ref_key(existing) != key for existing in refs):
        refs.append(ref)


def _object_ref_from_mapping(raw: Any) -> Optional[ObjectRef]:
    data = _as_dict(raw)
    if not data:
        return None
    if isinstance(data.get("ref"), dict):
        data = dict(data["ref"])
    owner_pack = _clean_str(
        data.get("owner_pack")
        or data.get("ownerPack")
        or data.get("capability_code")
        or data.get("capabilityCode")
    )
    object_kind = _clean_str(
        data.get("object_kind") or data.get("objectKind") or data.get("kind")
    )
    object_id = _clean_str(
        data.get("object_id") or data.get("objectId") or data.get("id")
    )
    uri = _clean_str(data.get("uri"))
    if not uri and owner_pack and object_kind and object_id:
        uri = f"mindscape://{owner_pack}/{object_kind}/{object_id}"
    if not (uri and owner_pack and object_kind and object_id):
        return None
    payload = {
        "uri": uri,
        "owner_pack": owner_pack,
        "object_kind": object_kind,
        "object_id": object_id,
    }
    for key in ("workspace_id", "version", "selector", "source_surface"):
        value = data.get(key) or data.get("workspaceId" if key == "workspace_id" else key)
        if value not in (None, "", [], {}):
            payload[key] = value
    try:
        return ObjectRef(**payload)
    except Exception:
        return None


def _selected_guidance_cards(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    action_parameters = metadata.get("action_parameters")
    if not isinstance(action_parameters, dict):
        action_parameters = {}
    cards: List[Dict[str, Any]] = []
    for raw in (
        metadata.get("selected_guidance_cards"),
        action_parameters.get("selected_guidance_cards"),
    ):
        if isinstance(raw, list):
            cards.extend(_as_dict(item) for item in raw if _as_dict(item))
    single_card = _as_dict(metadata.get("selected_guidance_card")) or _as_dict(
        action_parameters.get("selected_guidance_card")
    )
    if single_card:
        cards.append(single_card)

    guidance_id = _clean_str(
        metadata.get("selected_guidance_id") or action_parameters.get("selected_guidance_id")
    )
    guidance_metadata = _as_dict(
        metadata.get("selected_guidance_metadata")
        or action_parameters.get("selected_guidance_metadata")
    )
    if guidance_id or guidance_metadata:
        card = {
            "id": guidance_id,
            "metadata": guidance_metadata,
        }
        for key in ("command_template", "required_roles", "target_ref", "review_routes"):
            value = metadata.get(key) or action_parameters.get(f"selected_guidance_{key}")
            if value not in (None, "", [], {}):
                card[key] = value
        cards.append(card)
    return cards


def _selected_guidance_ids(
    metadata: Dict[str, Any],
    cards: Iterable[Dict[str, Any]],
) -> List[str]:
    action_parameters = metadata.get("action_parameters")
    if not isinstance(action_parameters, dict):
        action_parameters = {}
    ids: List[str] = []
    raw_ids = metadata.get("selected_guidance_ids") or action_parameters.get(
        "selected_guidance_ids"
    )
    if isinstance(raw_ids, list):
        ids.extend(str(item).strip() for item in raw_ids if str(item).strip())
    one_id = _clean_str(
        metadata.get("selected_guidance_id") or action_parameters.get("selected_guidance_id")
    )
    if one_id:
        ids.append(one_id)
    for card in cards:
        card_id = _clean_str(card.get("id") or card.get("guidance_id"))
        if card_id:
            ids.append(card_id)
    output: List[str] = []
    for item in ids:
        if item not in output:
            output.append(item)
    return output


def _candidate_from_guidance_card(
    card: Dict[str, Any],
    *,
    source: str,
) -> Optional[Dict[str, Any]]:
    metadata = _as_dict(card.get("metadata") or card.get("guidance_metadata"))
    pack_code = _clean_str(metadata.get("recommended_pack") or card.get("recommended_pack"))
    playbook_code = _clean_str(
        metadata.get("recommended_playbook") or card.get("recommended_playbook")
    )
    if not (pack_code or playbook_code):
        return None
    return {
        "source": source,
        "pack_code": pack_code,
        "playbook_code": playbook_code,
        "guidance_id": _clean_str(card.get("id") or card.get("guidance_id")),
        "object_ref": _as_dict(card.get("object_ref") or card.get("source_ref")),
        "confidence": metadata.get("confidence") or card.get("confidence") or "hint",
        "reason": _clean_str(card.get("title") or card.get("intent")) or "graph guidance",
    }


def _normalize_explicit_playbook_request(
    raw: Any,
    *,
    workspace_id: str,
    command: MeetingCommandRecord,
    context_attachments: List[Dict[str, Any]],
    aol_metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    data = _as_dict(raw)
    playbook_code = _clean_str(data.get("playbook_code"))
    if not playbook_code:
        return None

    input_params = _as_dict(data.get("input_params"))
    input_params.setdefault("workspace_id", workspace_id)
    input_params.setdefault("meeting_session_id", command.meeting_id)
    input_params.setdefault("task", command.intent_text)
    input_params.setdefault("human_instructions", command.intent_text)
    input_params.setdefault("addressable_object_layer", aol_metadata)
    quality_requirements = _as_dict(aol_metadata.get("quality_requirements"))
    if quality_requirements:
        input_params.setdefault("quality_requirements", quality_requirements)
    if context_attachments:
        input_params.setdefault("context_attachments", context_attachments)

    request: Dict[str, Any] = {
        "title": _clean_str(data.get("title")) or playbook_code,
        "description": _clean_str(data.get("description")) or command.intent_text,
        "playbook_code": playbook_code,
        "engine": _clean_str(data.get("engine")) or f"playbook:{playbook_code}",
        "priority": _clean_str(data.get("priority")) or "high",
        "intent_id": _clean_str(data.get("intent_id")) or f"PB_{playbook_code}",
        "input_params": input_params,
        "target_workspace_id": _clean_str(data.get("target_workspace_id")) or workspace_id,
        "preserve_atomic_playbook": data.get("preserve_atomic_playbook", True) is not False,
        "request_contract_source": _clean_str(data.get("request_contract_source"))
        or "explicit_playbook_request",
    }

    for field_name in (
        "replace_existing_playbook_codes",
        "replace_existing_codes",
        "handled_deliverable_ids",
        "deliverable_ids",
        "capability_profile",
        "requested_output_type",
    ):
        value = data.get(field_name)
        if value not in (None, "", [], {}):
            request[field_name] = value
    return request


def _truthy_flag(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _allow_requested_action_hard_playbook_request(
    *,
    metadata: Dict[str, Any],
    action_parameters: Dict[str, Any],
) -> tuple[bool, str]:
    if _truthy_flag(metadata.get("force_playbook_request")):
        return True, "metadata.force_playbook_request"
    if _truthy_flag(action_parameters.get("force_playbook_request")):
        return True, "action_parameters.force_playbook_request"
    if _truthy_flag(metadata.get("explicit_override")):
        if metadata.get("dispatch_mode") == "route_playbook":
            return True, "route_playbook.explicit_override"
        return True, "metadata.explicit_override"
    return False, "candidate_affordance_only"


def _collect_explicit_playbook_requests(
    *,
    metadata: Dict[str, Any],
    action_parameters: Dict[str, Any],
    requested_action: Any,
    workspace_id: str,
    command: MeetingCommandRecord,
    context_attachments: List[Dict[str, Any]],
    aol_metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    raw_requests: List[Any] = []
    for container in (metadata, action_parameters):
        for key in ("playbook_requests", "atomic_playbook_requests"):
            value = container.get(key)
            if isinstance(value, list):
                raw_requests.extend(value)
        for key in ("playbook_request", "atomic_playbook_request"):
            value = container.get(key)
            if isinstance(value, dict):
                raw_requests.append(value)

    if requested_action and requested_action.playbook_code:
        verb = _clean_str(getattr(requested_action, "verb", None)) or ""
        allowed, reason = _allow_requested_action_hard_playbook_request(
            metadata=metadata,
            action_parameters=action_parameters,
        )
        aol_metadata["hard_playbook_request_allowed"] = allowed
        aol_metadata["hard_playbook_request_reason"] = reason
        if allowed and verb in {"execute_playbook", "run_playbook", "invoke_playbook"}:
            raw_requests.append(
                {
                    "playbook_code": requested_action.playbook_code,
                    "input_params": dict(getattr(requested_action, "parameters", None) or {}),
                    "target_workspace_id": workspace_id,
                    "request_contract_source": "requested_action",
                }
            )

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for raw in raw_requests:
        request = _normalize_explicit_playbook_request(
            raw,
            workspace_id=workspace_id,
            command=command,
            context_attachments=context_attachments,
            aol_metadata=aol_metadata,
        )
        if not request:
            continue
        key = (
            str(request.get("playbook_code") or "").strip(),
            str(request.get("intent_id") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(request)
    return normalized


def _collect_candidate_playbook_input_defaults(
    *,
    candidate_playbooks: List[Dict[str, Any]],
    workspace_id: str,
    command: MeetingCommandRecord,
    context_attachments: List[Dict[str, Any]],
    aol_metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    defaults: List[Dict[str, Any]] = []
    seen = set()
    quality_requirements = _as_dict(aol_metadata.get("quality_requirements"))
    for candidate in candidate_playbooks:
        playbook_code = _clean_str(candidate.get("playbook_code"))
        if not playbook_code or playbook_code in seen:
            continue
        seen.add(playbook_code)
        input_params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "meeting_session_id": command.meeting_id,
            "task": command.intent_text,
            "human_instructions": command.intent_text,
            "addressable_object_layer": aol_metadata,
        }
        if quality_requirements:
            input_params["quality_requirements"] = quality_requirements
        if context_attachments:
            input_params["context_attachments"] = context_attachments
        defaults.append(
            {
                "playbook_code": playbook_code,
                "input_params": input_params,
                "request_contract_source": "candidate_playbook_defaults",
            }
        )
    return defaults


def _merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in dict(overlay or {}).items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _collect_quality_requirements(
    *,
    metadata: Dict[str, Any],
    action_parameters: Dict[str, Any],
    selected_cards: List[Dict[str, Any]],
    context_attachments: List[Dict[str, Any]],
    refs: List[ObjectRef],
) -> Dict[str, Any]:
    grounding_required = any(
        ref.owner_pack == "ig" and ref.object_kind == "reference" for ref in refs
    )
    requirements: Dict[str, Any] = {
        "schema_version": "generic_quality_requirements.v1",
        "source": "aol_meeting_orchestration_bridge",
        "producer_review_required": True,
        "grounding_required": grounding_required,
        "target": {"deliverable_kind": "storyboard_or_media_asset"},
        "content_quality": {
            "require_concrete_scene_copy": True,
            "reject_internal_workflow_copy": True,
            "require_reference_grounding": grounding_required,
        },
    }
    candidates: List[Dict[str, Any]] = []
    for container in (metadata, action_parameters):
        for key in (
            "quality_requirements",
            "content_quality_requirements",
            "producer_quality_requirements",
        ):
            candidate = _as_dict(container.get(key))
            if candidate:
                candidates.append(candidate)
    for card in selected_cards:
        card_payload = _as_dict(card)
        card_metadata = _as_dict(
            card_payload.get("metadata") or card_payload.get("guidance_metadata")
        )
        candidate = _as_dict(card_metadata.get("quality_requirements"))
        if candidate:
            candidates.append(candidate)
    for attachment in context_attachments:
        payload = _as_dict(attachment)
        for key in (
            "quality_requirements",
            "content_quality_requirements",
            "producer_quality_requirements",
        ):
            candidate = _as_dict(payload.get(key))
            if candidate:
                candidates.append(candidate)
    for candidate in candidates:
        requirements = _merge_dict(requirements, candidate)
    return requirements
