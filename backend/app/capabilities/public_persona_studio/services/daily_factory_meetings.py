from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..schema.daily_factory import EditorialMeetingRoundStartRequest
from .spatial_schedule_summary import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    resolve_spatial_schedule_artifact_ref,
    resolve_spatial_schedule_summary,
)
from .support import (
    load_artifact_payload,
    load_meeting_session_payload,
    load_workspace_payload,
    persist_data_artifact,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _load_ref_content(ref_value: Dict[str, Any]) -> Dict[str, Any]:
    artifact_id = str((ref_value or {}).get("artifact_id") or "").strip()
    if not artifact_id:
        return {}
    payload = load_artifact_payload(artifact_id)
    if not payload:
        return {}
    return dict(payload.get("content") or {})


def _artifact_ref(artifact: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if artifact and artifact.get("artifact_id"):
        return {"artifact_id": artifact.get("artifact_id")}
    return {}


def _meeting_kernel_ref(session_id: str) -> Dict[str, Any]:
    return {
        "kind": "meeting_session",
        "meeting_session_id": session_id,
    }


def _resolve_spatial_schedule_context_summary(
    *,
    workspace_id: str,
    meeting_session_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    workspace_payload = load_workspace_payload(workspace_id) or {}
    return resolve_spatial_schedule_summary(
        workspace_metadata=_as_dict(workspace_payload.get("metadata")),
        meeting_session_payload=meeting_session_payload,
    )


def _resolve_spatial_schedule_artifact_ref(summary: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_spatial_schedule_artifact_ref(summary)


def _build_round_1_agenda(
    *,
    ticket: Dict[str, Any],
    memo: Dict[str, Any],
) -> List[str]:
    storyline = str(ticket.get("storyline_candidate") or "daily_storyline").strip()
    push = str(ticket.get("what_to_push_today") or "today's reel").strip()
    memo_summary = str(memo.get("memo_summary") or "").strip()

    agenda = [
        f"Lock today's angle for {storyline}",
        f"Decide how to express: {push}",
        "Review persona fit, audience fit, and scene continuity",
    ]
    if memo_summary:
        agenda.append(f"Use inspiration memo: {memo_summary}")
    return agenda


def _build_round_2_agenda(
    *,
    brief: Dict[str, Any],
    editorial_packet: Dict[str, Any],
) -> List[str]:
    objective = str(_as_dict(brief.get("brief")).get("objective") or "").strip()
    storyline = str(editorial_packet.get("storyline_candidate") or "editorial_packet").strip()
    agenda = [
        f"Review and approve the editorial direction for {storyline}",
        "Check persona, scene continuity, and release readiness",
    ]
    if objective:
        agenda.insert(1, f"Verify the deliverable still matches objective: {objective}")
    return agenda


def _build_round_1_success_criteria(ticket: Dict[str, Any]) -> List[str]:
    criteria = [
        "Return one editorial angle that still sounds like this persona",
        "Return a bounded packet another workflow can consume",
    ]
    if str(ticket.get("scene_continuity_need") or "").strip():
        criteria.append("Preserve scene continuity as an explicit constraint")
    return criteria


def _build_round_2_success_criteria() -> List[str]:
    return [
        "Return a review decision that can move toward preview",
        "Record any blocking notes before approval/writeback",
    ]


def _build_round_1_editorial_packet(
    *,
    req: EditorialMeetingRoundStartRequest,
    foundation: Dict[str, Any],
    slate: Dict[str, Any],
    ticket: Dict[str, Any],
    memo: Dict[str, Any],
    session_id: str,
    spatial_requested: bool,
) -> Dict[str, Any]:
    return {
        "meeting_round": 1,
        "meeting_session_id": session_id,
        "kernel_ref": _meeting_kernel_ref(session_id),
        "foundation_snapshot_ref": dict(req.foundation_snapshot_ref or {}),
        "daily_slate_ref": dict(req.daily_slate_ref or {}),
        "daily_intent_ticket_ref": dict(req.daily_intent_ticket_ref or {}),
        "inspiration_memo_ref": dict(req.inspiration_memo_ref or {}),
        "storyline_candidate": str(ticket.get("storyline_candidate") or ""),
        "what_to_push_today": str(ticket.get("what_to_push_today") or ""),
        "desired_feeling": str(ticket.get("desired_feeling") or ""),
        "target_audience": str(ticket.get("target_audience") or ""),
        "scene_continuity_need": str(ticket.get("scene_continuity_need") or ""),
        "store_context_today": str(
            ticket.get("store_context_today") or slate.get("store_context_today") or ""
        ),
        "world_context_today": _as_dict(
            ticket.get("world_context_today") or slate.get("world_context_today")
        ),
        "world_card_projection": _as_dict(foundation.get("world_card_projection")),
        "shootable_material_today": _as_string_list(ticket.get("shootable_material_today")),
        "source_refs": list(memo.get("source_refs") or []),
        "fit_notes": _as_string_list(memo.get("fit_notes")),
        "conflict_notes": _as_string_list(memo.get("conflict_notes")),
        "borrowable_patterns": _as_string_list(memo.get("borrowable_patterns")),
        "avoid_patterns": _as_string_list(memo.get("avoid_patterns")),
        "scene_fit_notes": _as_string_list(memo.get("scene_fit_notes")),
        "memo_summary": str(memo.get("memo_summary") or ""),
        "governance_constraints": {
            "spatial_schedule": {
                "requested": spatial_requested,
                "targets": ["actor", "scene"],
            }
        },
        "deliverables": (
            [{"mime_type": SPATIAL_SCHEDULE_ARTIFACT_MIME, "name": "spatial_schedule"}]
            if spatial_requested
            else []
        ),
    }


def _build_round_1_digest(
    *,
    session_payload: Dict[str, Any],
    editorial_packet_artifact: Optional[Dict[str, Any]],
    spatial_summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "meeting_round": 1,
        "meeting_session_id": str(session_payload.get("id") or ""),
        "meeting_type": str(session_payload.get("meeting_type") or ""),
        "status": str(session_payload.get("status") or ""),
        "agenda": _as_string_list(session_payload.get("agenda")),
        "success_criteria": _as_string_list(session_payload.get("success_criteria")),
        "kernel_ref": _meeting_kernel_ref(str(session_payload.get("id") or "")),
        "editorial_packet_ref": _artifact_ref(editorial_packet_artifact),
        "spatial_schedule_artifact_ref": _resolve_spatial_schedule_artifact_ref(spatial_summary),
        "spatial_schedule_context_summary": spatial_summary,
    }


def _build_round_2_digest(
    *,
    session_payload: Dict[str, Any],
    editorial_packet_ref: Dict[str, Any],
    spatial_summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "meeting_round": 2,
        "meeting_session_id": str(session_payload.get("id") or ""),
        "meeting_type": str(session_payload.get("meeting_type") or ""),
        "status": str(session_payload.get("status") or ""),
        "agenda": _as_string_list(session_payload.get("agenda")),
        "success_criteria": _as_string_list(session_payload.get("success_criteria")),
        "kernel_ref": _meeting_kernel_ref(str(session_payload.get("id") or "")),
        "editorial_packet_ref": dict(editorial_packet_ref or {}),
        "spatial_schedule_artifact_ref": _resolve_spatial_schedule_artifact_ref(spatial_summary),
        "spatial_schedule_context_summary": spatial_summary,
    }


def _create_meeting_session(
    *,
    workspace_id: str,
    project_id: Optional[str],
    thread_id: Optional[str],
    meeting_type: str,
    agenda: List[str],
    success_criteria: List[str],
    max_rounds: int,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    from backend.app.models.meeting_session import MeetingSession
    from backend.app.services.stores.meeting_session_store import MeetingSessionStore

    store = MeetingSessionStore()
    existing = store.get_active_session(workspace_id, project_id, thread_id)
    if existing:
        store.end_session(existing.id)

    session = MeetingSession.new(
        workspace_id=workspace_id,
        project_id=project_id,
        thread_id=thread_id,
        meeting_type=meeting_type,
        agenda=agenda,
        success_criteria=success_criteria,
        max_rounds=max_rounds,
    )
    session.start()
    session.metadata = dict(metadata or {})
    store.create(session)
    if hasattr(session, "to_dict"):
        return session.to_dict()
    return dict(session or {})


async def start_editorial_meeting_round_1(
    request: EditorialMeetingRoundStartRequest | Dict[str, Any],
) -> Dict[str, Any]:
    req = (
        request
        if isinstance(request, EditorialMeetingRoundStartRequest)
        else EditorialMeetingRoundStartRequest.model_validate(request)
    )
    foundation = _load_ref_content(req.foundation_snapshot_ref)
    slate = _load_ref_content(req.daily_slate_ref)
    ticket = _load_ref_content(req.daily_intent_ticket_ref)
    memo = _load_ref_content(req.inspiration_memo_ref)

    scene_continuity_need = str(ticket.get("scene_continuity_need") or "").strip()
    spatial_requested = bool(
        ticket.get("spatial_schedule_requested") or scene_continuity_need
    )
    agenda = req.agenda_overrides or _build_round_1_agenda(ticket=ticket, memo=memo)
    success_criteria = req.success_criteria_overrides or _build_round_1_success_criteria(ticket)

    session_payload = _create_meeting_session(
        workspace_id=req.workspace_id,
        project_id=req.project_id,
        thread_id=req.thread_id,
        meeting_type="public_persona_editorial_round_1",
        agenda=agenda,
        success_criteria=success_criteria,
        max_rounds=req.max_rounds,
        metadata={
            "pps_stage": "editorial_round_1",
            "pps_meeting_round": 1,
            "seat_labels": list(req.seat_labels or ["Owner Voice", "Audience Seat", "Brand Guard", "Creative Director"]),
            "daily_factory_refs": {
                "foundation_snapshot_ref": dict(req.foundation_snapshot_ref or {}),
                "daily_slate_ref": dict(req.daily_slate_ref or {}),
                "daily_intent_ticket_ref": dict(req.daily_intent_ticket_ref or {}),
                "inspiration_memo_ref": dict(req.inspiration_memo_ref or {}),
            },
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": spatial_requested,
                    "targets": ["actor", "scene"],
                }
            },
            "scene_continuity_need": scene_continuity_need,
            "world_context_today": _as_dict(
                ticket.get("world_context_today") or slate.get("world_context_today")
            ),
            "metadata": dict(req.metadata or {}),
        },
    )

    editorial_packet = _build_round_1_editorial_packet(
        req=req,
        foundation=foundation,
        slate=slate,
        ticket=ticket,
        memo=memo,
        session_id=str(session_payload.get("id") or ""),
        spatial_requested=spatial_requested,
    )
    editorial_packet_artifact = persist_data_artifact(
        workspace_id=req.workspace_id,
        playbook_code="pps_editorial_meeting_round_1",
        title="Public Persona Editorial Packet",
        summary="Round 1 editorial packet for one daily storyline",
        content=editorial_packet,
        metadata={
            "kind": "editorial_packet",
            "meeting_round": 1,
            "meeting_session_id": str(session_payload.get("id") or ""),
            "storyline_candidate": str(ticket.get("storyline_candidate") or ""),
        },
    )
    spatial_summary = _resolve_spatial_schedule_context_summary(
        workspace_id=req.workspace_id,
        meeting_session_payload=load_meeting_session_payload(str(session_payload.get("id") or "")),
    )
    meeting_digest = _build_round_1_digest(
        session_payload=session_payload,
        editorial_packet_artifact=editorial_packet_artifact,
        spatial_summary=spatial_summary,
    )
    meeting_digest_artifact = persist_data_artifact(
        workspace_id=req.workspace_id,
        playbook_code="pps_editorial_meeting_round_1",
        title="Public Persona Meeting Digest Round 1",
        summary="Round 1 meeting launch digest for one daily storyline",
        content=meeting_digest,
        metadata={
            "kind": "meeting_digest_round_1",
            "meeting_session_id": str(session_payload.get("id") or ""),
            "storyline_candidate": str(ticket.get("storyline_candidate") or ""),
        },
    )
    return {
        "success": True,
        "meeting_session": session_payload,
        "kernel_ref": _meeting_kernel_ref(str(session_payload.get("id") or "")),
        "editorial_packet": editorial_packet,
        "meeting_digest_round_1": meeting_digest,
        "artifacts": {
            "editorial_packet_ref": _artifact_ref(editorial_packet_artifact),
            "meeting_digest_round_1_ref": _artifact_ref(meeting_digest_artifact),
        },
    }


async def start_editorial_meeting_round_2(
    request: EditorialMeetingRoundStartRequest | Dict[str, Any],
) -> Dict[str, Any]:
    req = (
        request
        if isinstance(request, EditorialMeetingRoundStartRequest)
        else EditorialMeetingRoundStartRequest.model_validate(request)
    )
    brief = _load_ref_content(req.public_expression_brief_ref)
    editorial_packet = _load_ref_content(req.editorial_packet_ref)

    agenda = req.agenda_overrides or _build_round_2_agenda(
        brief=brief,
        editorial_packet=editorial_packet,
    )
    success_criteria = req.success_criteria_overrides or _build_round_2_success_criteria()
    spatial_requested = bool(
        _as_dict(editorial_packet.get("governance_constraints"))
        .get("spatial_schedule", {})
        .get("requested")
    )

    session_payload = _create_meeting_session(
        workspace_id=req.workspace_id,
        project_id=req.project_id,
        thread_id=req.thread_id,
        meeting_type="public_persona_editorial_round_2",
        agenda=agenda,
        success_criteria=success_criteria,
        max_rounds=req.max_rounds,
        metadata={
            "pps_stage": "editorial_round_2",
            "pps_meeting_round": 2,
            "seat_labels": list(req.seat_labels or ["Owner Voice", "Persona Guard", "Review Chair"]),
            "daily_factory_refs": {
                "public_expression_brief_ref": dict(req.public_expression_brief_ref or {}),
                "editorial_packet_ref": dict(req.editorial_packet_ref or {}),
            },
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": spatial_requested,
                    "targets": ["actor", "scene"],
                }
            },
            "metadata": dict(req.metadata or {}),
        },
    )

    spatial_summary = _resolve_spatial_schedule_context_summary(
        workspace_id=req.workspace_id,
        meeting_session_payload=load_meeting_session_payload(str(session_payload.get("id") or "")),
    )
    meeting_digest = _build_round_2_digest(
        session_payload=session_payload,
        editorial_packet_ref=dict(req.editorial_packet_ref or {}),
        spatial_summary=spatial_summary,
    )
    meeting_digest_artifact = persist_data_artifact(
        workspace_id=req.workspace_id,
        playbook_code="pps_editorial_meeting_round_2",
        title="Public Persona Meeting Digest Round 2",
        summary="Round 2 review meeting digest for one daily storyline",
        content=meeting_digest,
        metadata={
            "kind": "meeting_digest_round_2",
            "meeting_session_id": str(session_payload.get("id") or ""),
        },
    )
    return {
        "success": True,
        "meeting_session": session_payload,
        "kernel_ref": _meeting_kernel_ref(str(session_payload.get("id") or "")),
        "meeting_digest_round_2": meeting_digest,
        "artifacts": {
            "meeting_digest_round_2_ref": _artifact_ref(meeting_digest_artifact),
        },
    }
