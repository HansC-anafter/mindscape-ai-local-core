"""Bridge Meeting Workbench command envelopes into MeetingEngine handoffs."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.handoff import HandoffIn
from backend.app.models.meeting_command import MeetingCommandEnvelope, MeetingCommandRecord
from backend.app.models.object_runtime import ObjectRef, ObjectSummary
from backend.app.models.object_runtime.graph import ObjectGraphProjectRequest
from backend.app.services.object_meeting_attachment_service import (
    ObjectMeetingAttachmentService,
    ObjectMeetingContextRecord,
)
from backend.app.services.object_runtime.resource_routing import build_resource_lane_request
from backend.app.services.object_runtime.route_services import project_object_graph
from backend.app.services.object_runtime.aol_meeting_orchestration_helpers import (
    _append_unique_ref,
    _as_dict,
    _candidate_from_guidance_card,
    _clean_str,
    _collect_candidate_playbook_input_defaults,
    _collect_explicit_playbook_requests,
    _collect_quality_requirements,
    _object_ref_from_mapping,
    _ref_key,
    _selected_guidance_cards,
    _selected_guidance_ids,
)
from backend.app.services.orchestration.meeting.meeting_command_authority import (
    SERVER_AUTHORITY_METADATA_KEY,
    read_server_authority,
)


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
        server_authority = read_server_authority(command.metadata)
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
            "active_group_id": canonical.active_group_id,
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

        quality_requirements = _collect_quality_requirements(
            metadata=metadata,
            action_parameters=action_parameters,
            selected_cards=selected_cards,
            context_attachments=context_attachments,
            refs=refs,
        )
        aol_metadata["quality_requirements"] = quality_requirements
        resource_lane_request = build_resource_lane_request(
            workspace_id=workspace_id,
            aol_metadata=aol_metadata,
            action_parameters=action_parameters,
        )
        if resource_lane_request:
            aol_metadata["resource_lane_request"] = resource_lane_request
        playbook_requests = _collect_explicit_playbook_requests(
            metadata=metadata,
            action_parameters=action_parameters,
            requested_action=requested,
            workspace_id=workspace_id,
            command=command,
            context_attachments=context_attachments,
            aol_metadata=aol_metadata,
        )
        playbook_input_defaults = _collect_candidate_playbook_input_defaults(
            candidate_playbooks=candidate_playbooks,
            workspace_id=workspace_id,
            command=command,
            context_attachments=context_attachments,
            aol_metadata=aol_metadata,
        )
        governance_constraints = {
            "addressable_object_layer": aol_metadata,
            "quality_requirements": quality_requirements,
        }
        if resource_lane_request:
            governance_constraints["resource_lane_request"] = resource_lane_request

        explicit_grounded_answer = (
            "grounded_knowledge_answer" in set(canonical.expected_outputs)
            or (
                canonical.requested_action is not None
                and canonical.requested_action.verb == "answer_with_knowledge"
            )
        )
        grounded_answer_request = (
            {
                "question": command.intent_text,
                "retrieval_modes": list(
                    (
                        canonical.requested_action.parameters.get(
                            "retrieval_modes",
                            [],
                        )
                        if canonical.requested_action is not None
                        else []
                    )
                ),
                "scope": (
                    "active_group"
                    if canonical.active_group_id
                    else "workspace"
                ),
                "frontier_preview": bool(
                    canonical.requested_action
                    and canonical.requested_action.parameters.get(
                        "frontier_preview"
                    )
                ),
            }
            if explicit_grounded_answer
            else None
        )

        return HandoffIn(
            handoff_id=f"aol_cmd_{command.command_id}_{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            intent_summary=command.intent_text,
            goals=[command.intent_text],
            governance_constraints=governance_constraints,
            context_attachments=context_attachments,
            human_instructions=command.intent_text
            or metadata.get("raw_intent_text")
            or canonical.intent_text,
            playbook_requests=playbook_requests or None,
            playbook_input_defaults=playbook_input_defaults or None,
            metadata={
                "addressable_object_layer": aol_metadata,
                "quality_requirements": quality_requirements,
                SERVER_AUTHORITY_METADATA_KEY: server_authority.model_dump(
                    mode="json"
                ),
                **(
                    {"grounded_knowledge_answer": grounded_answer_request}
                    if grounded_answer_request is not None
                    else {}
                ),
                **({"resource_lane_request": resource_lane_request} if resource_lane_request else {}),
            },
        )
