"""Bridge Meeting Workbench command envelopes into MeetingEngine handoffs."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.handoff import HandoffIn
from backend.app.models.meeting_command import MeetingCommandEnvelope, MeetingCommandRecord
from backend.app.models.object_runtime import ObjectRef, ObjectSummary
from backend.app.models.object_runtime.graph import ObjectGraphProjectRequest
from backend.app.services.object_meeting_attachment_service import (
    ObjectMeetingAttachmentService,
    ObjectMeetingContextRecord,
)
from backend.app.services.object_runtime.route_services import project_object_graph


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _model_dump(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return dict(value) if isinstance(value, dict) else {}


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
    object_kind = _clean_str(data.get("object_kind") or data.get("objectKind") or data.get("kind"))
    object_id = _clean_str(data.get("object_id") or data.get("objectId") or data.get("id"))
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


def _selected_guidance_ids(metadata: Dict[str, Any], cards: Iterable[Dict[str, Any]]) -> List[str]:
    action_parameters = metadata.get("action_parameters")
    if not isinstance(action_parameters, dict):
        action_parameters = {}
    ids: List[str] = []
    raw_ids = metadata.get("selected_guidance_ids") or action_parameters.get("selected_guidance_ids")
    if isinstance(raw_ids, list):
        ids.extend(str(item).strip() for item in raw_ids if str(item).strip())
    one_id = _clean_str(metadata.get("selected_guidance_id") or action_parameters.get("selected_guidance_id"))
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


def _candidate_from_guidance_card(card: Dict[str, Any], *, source: str) -> Optional[Dict[str, Any]]:
    metadata = _as_dict(card.get("metadata") or card.get("guidance_metadata"))
    pack_code = _clean_str(metadata.get("recommended_pack") or card.get("recommended_pack"))
    playbook_code = _clean_str(metadata.get("recommended_playbook") or card.get("recommended_playbook"))
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


class AOLMeetingOrchestrationBridge:
    """Build generic MeetingEngine handoffs from AOL command context."""

    def __init__(self, attachment_service: Optional[ObjectMeetingAttachmentService] = None) -> None:
        self._attachment_service = attachment_service or ObjectMeetingAttachmentService()

    async def build_handoff_in(
        self,
        *,
        command: MeetingCommandRecord,
        canonical: MeetingCommandEnvelope,
        session: Any,
        workspace_id: str,
    ) -> HandoffIn:
        metadata = dict(canonical.metadata or {})
        action_parameters = metadata.get("action_parameters")
        if not isinstance(action_parameters, dict):
            action_parameters = {}

        refs: List[ObjectRef] = []
        role_by_uri: Dict[str, str] = {}
        for entry in canonical.context_objects:
            _append_unique_ref(refs, entry.ref)
            role_by_uri[_ref_key(entry.ref)] = entry.role
        for mention in canonical.meeting_mentions or []:
            ref = _object_ref_from_mapping(mention)
            if ref is None:
                continue
            _append_unique_ref(refs, ref)
            role_by_uri.setdefault(_ref_key(ref), _clean_str(mention.get("role")) or "source")
        selected_guidance_refs: List[ObjectRef] = []
        selected_ref = _object_ref_from_mapping(
            metadata.get("selected_guidance_object_ref")
            or action_parameters.get("selected_guidance_object_ref")
        )
        if selected_ref is not None:
            _append_unique_ref(refs, selected_ref)
            selected_guidance_refs.append(selected_ref)
            role_by_uri.setdefault(_ref_key(selected_ref), "source")

        projections = []
        if refs:
            graph_response = await project_object_graph(
                ObjectGraphProjectRequest(
                    objects=refs,
                    include_relations=True,
                    include_summaries=True,
                ),
                workspace_id=workspace_id,
            )
            projections = list(graph_response.projections or [])

        projection_by_uri = {_ref_key(projection.ref): projection for projection in projections}
        context_records: List[ObjectMeetingContextRecord] = []
        for ref in refs:
            projection = projection_by_uri.get(_ref_key(ref))
            summary = (
                projection.summary
                if projection and projection.summary
                else ObjectSummary(
                    ref=ref,
                    title=ref.object_id,
                    summary_text=f"{ref.owner_pack}.{ref.object_kind}:{ref.object_id}",
                )
            )
            context_records.append(
                ObjectMeetingContextRecord(
                    role=role_by_uri.get(_ref_key(ref), "source"),
                    ref=ref,
                    summary=summary,
                    meeting_projection=(
                        projection.model_dump(exclude_none=True) if projection else None
                    ),
                )
            )

        if context_records:
            build_result = self._attachment_service.build_handoff(
                workspace_id=workspace_id,
                meeting_id=command.meeting_id,
                meeting_type=getattr(session, "meeting_type", None) or "meeting_workbench",
                intent_summary=command.intent_text,
                write_mode=canonical.write_mode,
                context_objects=context_records,
            )
            context_attachments = list(build_result.context_attachments)
        else:
            context_attachments = []

        selected_cards = _selected_guidance_cards(metadata)
        selected_ids = _selected_guidance_ids(metadata, selected_cards)
        candidate_playbooks: List[Dict[str, Any]] = []
        requested = canonical.requested_action
        if requested and (requested.pack_code or requested.playbook_code):
            candidate_playbooks.append(
                {
                    "source": "selected_pack_tool",
                    "pack_code": requested.pack_code,
                    "playbook_code": requested.playbook_code,
                    "guidance_id": None,
                    "object_ref": None,
                    "confidence": "user_selected",
                    "reason": "selected pack tool",
                }
            )
        for card in selected_cards:
            candidate = _candidate_from_guidance_card(card, source="selected_guidance")
            if candidate:
                candidate_playbooks.append(candidate)

        guidance_by_uri: Dict[str, List[Dict[str, Any]]] = {}
        for projection in projections:
            cards = []
            for guidance in projection.guidance or []:
                card = guidance.model_dump(exclude_none=True)
                cards.append(card)
                candidate = _candidate_from_guidance_card(card, source="graph_guidance")
                if candidate:
                    candidate["object_ref"] = projection.ref.model_dump(exclude_none=True)
                    candidate_playbooks.append(candidate)
            if cards:
                guidance_by_uri[_ref_key(projection.ref)] = cards

        for attachment in context_attachments:
            ref = _object_ref_from_mapping(attachment.get("object_ref"))
            if ref is None:
                continue
            cards = guidance_by_uri.get(_ref_key(ref), [])
            if cards:
                attachment["guidance_hints"] = cards
                attachment["review_routes"] = [
                    route
                    for card in cards
                    for route in list(card.get("review_routes") or [])
                    if route
                ]
        if selected_cards:
            context_attachments.append(
                {
                    "attachment_id": f"att_guidance_{uuid.uuid4().hex[:16]}",
                    "role": "guidance",
                    "verb": "select_guidance",
                    "selected_guidance": selected_ids,
                    "selected_guidance_metadata": [
                        _as_dict(card.get("metadata") or card.get("guidance_metadata"))
                        for card in selected_cards
                    ],
                    "guidance_hints": selected_cards,
                    "owner_pack": None,
                }
            )

        role_object_uris: Dict[str, List[str]] = {}
        for record in context_records:
            role_object_uris.setdefault(record.role, [])
            if record.ref.uri not in role_object_uris[record.role]:
                role_object_uris[record.role].append(record.ref.uri)

        aol_metadata = {
            "command_id": command.command_id,
            "meeting_id": command.meeting_id,
            "origin_surface": canonical.origin_surface,
            "write_mode": canonical.write_mode,
            "selected_object_refs": [ref.model_dump(exclude_none=True) for ref in refs],
            "selected_guidance_ids": selected_ids,
            "selected_guidance_cards": selected_cards,
            "selected_guidance_metadata": [
                _as_dict(card.get("metadata") or card.get("guidance_metadata"))
                for card in selected_cards
            ],
            "selected_guidance_object_refs": [
                ref.model_dump(exclude_none=True) for ref in selected_guidance_refs
            ],
            "candidate_playbooks": candidate_playbooks,
            "explicit_override": bool(metadata.get("explicit_override")),
            "role_object_uris": role_object_uris,
        }
        existing_session_aol = _as_dict((getattr(session, "metadata", {}) or {}).get("addressable_object_layer"))
        if existing_session_aol:
            aol_metadata["session_addressable_object_layer"] = existing_session_aol

        return HandoffIn(
            handoff_id=f"aol_cmd_{command.command_id}_{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            intent_summary=command.intent_text,
            goals=[command.intent_text],
            governance_constraints={"addressable_object_layer": aol_metadata},
            context_attachments=context_attachments,
            human_instructions=metadata.get("raw_intent_text") or command.intent_text,
            metadata={"addressable_object_layer": aol_metadata},
        )
