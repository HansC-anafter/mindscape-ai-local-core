from __future__ import annotations

from typing import Any, Dict, List, Optional

from .support import (
    list_artifact_payloads_by_playbook,
    load_artifact_payload,
    load_meeting_session_payload,
    load_workspace_payload,
)
from .spatial_schedule_summary import (
    resolve_spatial_schedule_artifact_ref,
    resolve_spatial_schedule_summary,
)


def _latest_artifact(
    workspace_id: str,
    playbook_code: str,
    *,
    metadata_kind: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    artifacts = list_artifact_payloads_by_playbook(workspace_id, playbook_code)
    if not metadata_kind:
        return artifacts[0] if artifacts else None
    for artifact in artifacts:
        metadata = dict(artifact.get("metadata") or {})
        if metadata.get("kind") == metadata_kind:
            return artifact
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _as_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _collect_preview_output_refs(preview_artifact: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not preview_artifact:
        return []
    content = _as_dict(preview_artifact.get("content"))
    preview_result = _as_dict(content.get("preview_result"))

    refs: List[Dict[str, Any]] = []
    seen = set()

    def add_ref(candidate: Dict[str, Any]) -> None:
        if not candidate:
            return
        key = "|".join(
            [
                str(candidate.get("artifact_id") or ""),
                str(candidate.get("storage_key") or ""),
                str(candidate.get("local_path") or ""),
                str(candidate.get("url") or ""),
            ]
        ).strip("|")
        if not key or key in seen:
            return
        seen.add(key)
        refs.append(candidate)

    add_ref(_as_dict(content.get("artifact")))
    add_ref(_as_dict(preview_result.get("preview_clip_ref")))
    for clip_ref in _as_list_of_dicts(preview_result.get("clip_refs")):
        add_ref(clip_ref)
    return refs


def _artifact_ref(artifact: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if artifact and artifact.get("artifact_id"):
        return {"artifact_id": artifact.get("artifact_id")}
    return {}


def _resolve_daily_factory_results(workspace_id: str) -> Dict[str, Any]:
    daily_slate_artifact = _latest_artifact(
        workspace_id,
        "pps_daily_slate",
        metadata_kind="daily_slate",
    )
    daily_intent_artifact = _latest_artifact(
        workspace_id,
        "pps_daily_intent_ticket",
        metadata_kind="daily_intent_ticket",
    )
    inspiration_artifact = _latest_artifact(
        workspace_id,
        "pps_inspiration_intake",
        metadata_kind="inspiration_memo",
    )

    daily_slate = _as_dict((daily_slate_artifact or {}).get("content"))
    daily_intent_ticket = _as_dict((daily_intent_artifact or {}).get("content"))
    inspiration_memo = _as_dict((inspiration_artifact or {}).get("content"))

    slot_summaries = []
    for slot in _as_list_of_dicts(daily_slate.get("slots")):
        slot_summaries.append(
            {
                "slot_id": str(slot.get("slot_id") or ""),
                "label": str(slot.get("label") or ""),
                "storyline": str(slot.get("storyline") or ""),
                "priority": int(slot.get("priority") or 0),
                "status": str(slot.get("status") or "planned"),
            }
        )

    return {
        "daily_slate_artifact": daily_slate_artifact,
        "daily_intent_artifact": daily_intent_artifact,
        "inspiration_artifact": inspiration_artifact,
        "summary": {
            "current_slate": daily_slate or None,
            "slot_summaries": slot_summaries,
            "latest_intent_ticket": daily_intent_ticket or None,
            "latest_inspiration_memo": inspiration_memo or None,
        },
    }


def _resolve_spatial_summary(
    *,
    workspace_id: str,
    meeting_session_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    workspace_payload = load_workspace_payload(workspace_id) or {}
    return resolve_spatial_schedule_summary(
        workspace_metadata=_as_dict(workspace_payload.get("metadata")),
        meeting_session_payload=meeting_session_payload,
    )


def _resolve_spatial_artifact_ref(summary: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_spatial_schedule_artifact_ref(summary)


def _resolve_editorial_meeting_results(workspace_id: str) -> Dict[str, Any]:
    round_1_digest_artifact = _latest_artifact(
        workspace_id,
        "pps_editorial_meeting_round_1",
        metadata_kind="meeting_digest_round_1",
    )
    editorial_packet_artifact = _latest_artifact(
        workspace_id,
        "pps_editorial_meeting_round_1",
        metadata_kind="editorial_packet",
    )
    round_2_digest_artifact = _latest_artifact(
        workspace_id,
        "pps_editorial_meeting_round_2",
        metadata_kind="meeting_digest_round_2",
    )

    round_1_digest = _as_dict((round_1_digest_artifact or {}).get("content"))
    editorial_packet = _as_dict((editorial_packet_artifact or {}).get("content"))
    round_2_digest = _as_dict((round_2_digest_artifact or {}).get("content"))

    round_2_session_payload = load_meeting_session_payload(
        str(round_2_digest.get("meeting_session_id") or "")
    )
    round_1_session_payload = load_meeting_session_payload(
        str(round_1_digest.get("meeting_session_id") or "")
    )
    spatial_summary = _resolve_spatial_summary(
        workspace_id=workspace_id,
        meeting_session_payload=round_2_session_payload or round_1_session_payload,
    )

    return {
        "round_1_digest_artifact": round_1_digest_artifact,
        "editorial_packet_artifact": editorial_packet_artifact,
        "round_2_digest_artifact": round_2_digest_artifact,
        "summary": {
            "latest_meeting_round_1": round_1_digest or None,
            "editorial_packet": editorial_packet or None,
            "latest_meeting_round_2": round_2_digest or None,
            "spatial_schedule_context_summary": spatial_summary or None,
            "spatial_schedule_artifact_ref": _resolve_spatial_artifact_ref(
                spatial_summary
            ),
        },
    }


def _resolve_approval_result(
    workspace_id: str,
    preview_artifact: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    approval_artifact = _latest_artifact(
        workspace_id,
        "pps_approval_writeback",
        metadata_kind="approval_receipt",
    )
    if not approval_artifact:
        selected_output_refs = _collect_preview_output_refs(preview_artifact)
        return {
            "approval_result": None,
            "approval_artifact": None,
            "distribution_handoff": None,
            "distribution_handoff_ref": {},
            "selected_output_refs": selected_output_refs,
            "distribution_targets": [],
            "measurement_focus": [],
            "approval_status": "",
            "alignment_result": None,
            "writeback_result": None,
            "request_snapshot": {},
            "release_readiness": {
                "selected_output_count": len(selected_output_refs),
                "approval_status": "not_recorded",
                "alignment_label": "not_checked",
                "writeback_label": "not_run",
                "distribution_status": "not_created",
                "distribution_targets": [],
                "measurement_focus": [],
            },
        }

    receipt = _as_dict(approval_artifact.get("content"))
    receipt_metadata = _as_dict(receipt.get("metadata"))
    alignment_result = receipt_metadata.get("alignment_result")
    writeback_result = receipt_metadata.get("writeback_result")
    request_snapshot = _as_dict(receipt_metadata.get("request_snapshot"))
    distribution_handoff_ref = _as_dict(receipt.get("distribution_handoff_ref"))
    distribution_handoff = None
    handoff_artifact_id = str(distribution_handoff_ref.get("artifact_id") or "").strip()
    if handoff_artifact_id:
        handoff_payload = load_artifact_payload(handoff_artifact_id)
        distribution_handoff = _as_dict((handoff_payload or {}).get("content"))
    if not distribution_handoff:
        distribution_artifact = _latest_artifact(
            workspace_id,
            "pps_approval_writeback",
            metadata_kind="distribution_handoff",
        )
        distribution_handoff = _as_dict((distribution_artifact or {}).get("content"))

    selected_output_refs = _as_list_of_dicts(receipt.get("selected_output_refs"))
    if not selected_output_refs:
        selected_output_refs = _collect_preview_output_refs(preview_artifact)

    distribution_targets = [str(item) for item in distribution_handoff.get("distribution_targets") or []]
    measurement_focus = [str(item) for item in distribution_handoff.get("measurement_focus") or []]

    alignment_label = "not_checked"
    if isinstance(alignment_result, dict):
        if alignment_result.get("success") is True:
            result_payload = _as_dict(alignment_result.get("result"))
            alignment_label = "aligned" if result_payload.get("is_aligned") is not False else "review_needed"
        elif alignment_result:
            alignment_label = "review_needed"

    writeback_label = "not_run"
    if isinstance(writeback_result, dict) and writeback_result:
        writeback_label = "writeback_ok" if writeback_result.get("success") is True else "writeback_failed"
    elif receipt.get("writeback_mode") == "local_only":
        writeback_label = "local_only"

    distribution_status = (
        str(distribution_handoff.get("status") or distribution_handoff_ref.get("status") or "not_created")
        if distribution_handoff or distribution_handoff_ref
        else "not_created"
    )

    approval_result = {
        "approval_receipt": receipt,
        "alignment_result": alignment_result,
        "writeback_result": writeback_result,
        "distribution_handoff": distribution_handoff or None,
        "distribution_targets": distribution_targets,
        "measurement_focus": measurement_focus,
        "selected_output_refs": selected_output_refs,
        "artifact": approval_artifact,
    }

    return {
        "approval_result": approval_result,
        "approval_artifact": approval_artifact,
        "distribution_handoff": distribution_handoff or None,
        "distribution_handoff_ref": distribution_handoff_ref,
        "selected_output_refs": selected_output_refs,
        "distribution_targets": distribution_targets,
        "measurement_focus": measurement_focus,
        "approval_status": str(receipt.get("approval_status") or ""),
        "alignment_result": alignment_result,
        "writeback_result": writeback_result,
        "request_snapshot": request_snapshot,
        "release_readiness": {
            "selected_output_count": len(selected_output_refs),
            "approval_status": str(receipt.get("approval_status") or "recorded"),
            "alignment_label": alignment_label,
            "writeback_label": writeback_label,
            "distribution_status": distribution_status,
            "distribution_targets": distribution_targets,
            "measurement_focus": measurement_focus,
        },
    }


def _derive_hydrate_inputs(
    *,
    workspace_id: str,
    daily_factory_resolution: Dict[str, Any],
    editorial_meeting_resolution: Dict[str, Any],
    foundation_artifact: Optional[Dict[str, Any]],
    brief_artifact: Optional[Dict[str, Any]],
    preview_artifact: Optional[Dict[str, Any]],
    approval_resolution: Dict[str, Any],
) -> Dict[str, Any]:
    foundation_content = _as_dict((foundation_artifact or {}).get("content"))
    brief_content = _as_dict((brief_artifact or {}).get("content"))
    brief = _as_dict(brief_content.get("brief"))
    preview_content = _as_dict((preview_artifact or {}).get("content"))
    preview_request = _as_dict(preview_content.get("request"))
    request_snapshot = _as_dict(approval_resolution.get("request_snapshot"))
    approval_result = _as_dict(approval_resolution.get("approval_result"))
    approval_receipt = _as_dict(approval_result.get("approval_receipt"))
    current_slate = _as_dict(daily_factory_resolution.get("summary", {}).get("current_slate"))
    latest_intent_ticket = _as_dict(
        daily_factory_resolution.get("summary", {}).get("latest_intent_ticket")
    )
    latest_inspiration_memo = _as_dict(
        daily_factory_resolution.get("summary", {}).get("latest_inspiration_memo")
    )
    latest_round_1_digest = _as_dict(
        editorial_meeting_resolution.get("summary", {}).get("latest_meeting_round_1")
    )
    latest_round_2_digest = _as_dict(
        editorial_meeting_resolution.get("summary", {}).get("latest_meeting_round_2")
    )
    editorial_packet = _as_dict(
        editorial_meeting_resolution.get("summary", {}).get("editorial_packet")
    )
    spatial_summary = _as_dict(
        editorial_meeting_resolution.get("summary", {}).get(
            "spatial_schedule_context_summary"
        )
    )

    mind_lens_context = _as_dict(foundation_content.get("mind_lens_context"))
    source_refs = _as_dict(foundation_content.get("source_refs"))
    personal_universe_ref = _as_dict(source_refs.get("personal_universe"))
    scene_package_selector = _as_dict(preview_request.get("scene_package_selector"))

    return {
        "foundation": {
            "workspace_id": str(foundation_content.get("workspace_id") or workspace_id),
            "foundation_mode": str(
                foundation_content.get("foundation_mode") or "hybrid"
            ),
            "user_id": str(
                mind_lens_context.get("user_id")
                or personal_universe_ref.get("user_id")
                or ""
            ),
            "role_hint": str(mind_lens_context.get("role_hint") or ""),
            "governance_context_summary": _as_dict(
                foundation_content.get("governance_context_summary")
            ),
            "selected_memory_packet_summary": _as_dict(
                foundation_content.get("selected_memory_packet_summary")
            ),
            "world_card_projection": _as_dict(
                foundation_content.get("world_card_projection")
            ),
        },
        "brief": {
            "audience": str(brief.get("audience") or ""),
            "channel": str(brief.get("channel") or ""),
            "objective": str(brief.get("objective") or ""),
            "message_core": _as_string_list(brief.get("message_core")),
            "distribution_targets": _as_string_list(
                brief.get("distribution_targets")
            ),
            "measurement_focus": _as_string_list(brief.get("measurement_focus")),
        },
        "preview": {
            "session_id": str(preview_request.get("session_id") or ""),
            "scene_package_artifact_id": str(
                scene_package_selector.get("artifact_id") or ""
            ),
            "source_type": str(preview_request.get("source_type") or "generative"),
            "prompt": str(preview_request.get("prompt") or ""),
        },
        "approval": {
            "approval_status": str(
                approval_resolution.get("approval_status") or "approved"
            ),
            "reviewer_note": str(approval_receipt.get("reviewer_note") or ""),
            "channel_targets": _as_string_list(
                request_snapshot.get("channel_targets")
                or approval_receipt.get("channel_targets")
            ),
            "writeback_mode": str(
                request_snapshot.get("writeback_mode")
                or approval_receipt.get("writeback_mode")
                or "local_only"
            ),
            "writeback_payload": _as_dict(request_snapshot.get("writeback_payload")),
            "alignment_content": str(
                request_snapshot.get("content_for_alignment") or ""
            ),
        },
        "daily_factory": {
            "slate": {
                "workspace_id": str(current_slate.get("workspace_id") or workspace_id),
                "slate_date": str(current_slate.get("slate_date") or ""),
                "store_context_today": str(current_slate.get("store_context_today") or ""),
                "world_context_today": _as_dict(current_slate.get("world_context_today")),
                "capacity_today": int(current_slate.get("capacity_today") or 0),
                "constraints_today": _as_string_list(current_slate.get("constraints_today")),
                "active_storylines": _as_string_list(current_slate.get("active_storylines")),
                "slots": _as_list_of_dicts(current_slate.get("slots")),
            },
            "intent_ticket": {
                "daily_slate_artifact_id": str(
                    _artifact_ref(daily_factory_resolution.get("daily_slate_artifact")).get("artifact_id") or ""
                ),
                "slot_id": str(latest_intent_ticket.get("slot_id") or ""),
                "what_to_push_today": str(latest_intent_ticket.get("what_to_push_today") or ""),
                "desired_feeling": str(latest_intent_ticket.get("desired_feeling") or ""),
                "target_audience": str(latest_intent_ticket.get("target_audience") or ""),
                "shootable_material_today": _as_string_list(
                    latest_intent_ticket.get("shootable_material_today")
                ),
                "constraints_today": _as_string_list(latest_intent_ticket.get("constraints_today")),
                "storyline_candidate": str(latest_intent_ticket.get("storyline_candidate") or ""),
                "scene_continuity_need": str(
                    latest_intent_ticket.get("scene_continuity_need") or ""
                ),
                "spatial_schedule_requested": bool(
                    latest_intent_ticket.get("spatial_schedule_requested") or False
                ),
            },
            "inspiration_memo": {
                "daily_intent_ticket_artifact_id": str(
                    _artifact_ref(daily_factory_resolution.get("daily_intent_artifact")).get("artifact_id") or ""
                ),
                "source_lane": str(latest_inspiration_memo.get("source_lane") or ""),
                "source_refs": _as_list_of_dicts(latest_inspiration_memo.get("source_refs")),
                "fit_notes": _as_string_list(latest_inspiration_memo.get("fit_notes")),
                "conflict_notes": _as_string_list(latest_inspiration_memo.get("conflict_notes")),
                "borrowable_patterns": _as_string_list(
                    latest_inspiration_memo.get("borrowable_patterns")
                ),
                "avoid_patterns": _as_string_list(latest_inspiration_memo.get("avoid_patterns")),
                "scene_fit_notes": _as_string_list(latest_inspiration_memo.get("scene_fit_notes")),
                "memo_summary": str(latest_inspiration_memo.get("memo_summary") or ""),
            },
            "meeting_round_1": {
                "meeting_session_id": str(latest_round_1_digest.get("meeting_session_id") or ""),
                "editorial_packet_artifact_id": str(
                    _artifact_ref(
                        editorial_meeting_resolution.get("editorial_packet_artifact")
                    ).get("artifact_id")
                    or ""
                ),
                "agenda": _as_string_list(latest_round_1_digest.get("agenda")),
                "success_criteria": _as_string_list(
                    latest_round_1_digest.get("success_criteria")
                ),
                "status": str(latest_round_1_digest.get("status") or ""),
            },
            "meeting_round_2": {
                "meeting_session_id": str(latest_round_2_digest.get("meeting_session_id") or ""),
                "agenda": _as_string_list(latest_round_2_digest.get("agenda")),
                "success_criteria": _as_string_list(
                    latest_round_2_digest.get("success_criteria")
                ),
                "status": str(latest_round_2_digest.get("status") or ""),
            },
            "editorial_packet": {
                "storyline_candidate": str(editorial_packet.get("storyline_candidate") or ""),
                "what_to_push_today": str(editorial_packet.get("what_to_push_today") or ""),
                "scene_continuity_need": str(
                    editorial_packet.get("scene_continuity_need") or ""
                ),
                "memo_summary": str(editorial_packet.get("memo_summary") or ""),
                "governance_constraints": _as_dict(
                    editorial_packet.get("governance_constraints")
                ),
            },
            "spatial_schedule": {
                "summary": spatial_summary,
                "artifact_ref": editorial_meeting_resolution.get("summary", {}).get(
                    "spatial_schedule_artifact_ref"
                )
                or {},
            },
        },
    }


async def get_workbench_state(workspace_id: str) -> Dict[str, Any]:
    daily_factory_resolution = _resolve_daily_factory_results(workspace_id)
    editorial_meeting_resolution = _resolve_editorial_meeting_results(workspace_id)
    foundation_artifact = _latest_artifact(
        workspace_id,
        "pps_foundation_sync",
        metadata_kind="foundation_snapshot",
    )
    brief_artifact = _latest_artifact(
        workspace_id,
        "pps_expression_brief",
        metadata_kind="public_expression_bundle",
    )
    preview_artifact = _latest_artifact(
        workspace_id,
        "pps_storyboard_preview",
        metadata_kind="preview_run",
    )

    approval_resolution = _resolve_approval_result(workspace_id, preview_artifact)

    artifact_refs = {
        "daily_slate_ref": _artifact_ref(daily_factory_resolution.get("daily_slate_artifact")),
        "daily_intent_ticket_ref": _artifact_ref(daily_factory_resolution.get("daily_intent_artifact")),
        "inspiration_memo_ref": _artifact_ref(daily_factory_resolution.get("inspiration_artifact")),
        "meeting_digest_round_1_ref": _artifact_ref(
            editorial_meeting_resolution.get("round_1_digest_artifact")
        ),
        "editorial_packet_ref": _artifact_ref(
            editorial_meeting_resolution.get("editorial_packet_artifact")
        ),
        "meeting_digest_round_2_ref": _artifact_ref(
            editorial_meeting_resolution.get("round_2_digest_artifact")
        ),
        "spatial_schedule_artifact_ref": editorial_meeting_resolution.get(
            "summary", {}
        ).get("spatial_schedule_artifact_ref")
        or {},
        "foundation_snapshot_ref": _artifact_ref(foundation_artifact),
        "public_expression_brief_ref": _artifact_ref(brief_artifact),
        "preview_artifact_ref": _artifact_ref(preview_artifact),
        "approval_receipt_ref": _artifact_ref(approval_resolution.get("approval_artifact")),
        "distribution_handoff_ref": approval_resolution.get("distribution_handoff_ref") or {},
    }

    return {
        "success": True,
        "workspace_id": workspace_id,
        "latest_results": {
            "daily_slate_result": daily_factory_resolution.get("daily_slate_artifact"),
            "daily_intent_result": daily_factory_resolution.get("daily_intent_artifact"),
            "inspiration_result": daily_factory_resolution.get("inspiration_artifact"),
            "meeting_round_1_result": editorial_meeting_resolution.get(
                "round_1_digest_artifact"
            ),
            "editorial_packet_result": editorial_meeting_resolution.get(
                "editorial_packet_artifact"
            ),
            "meeting_round_2_result": editorial_meeting_resolution.get(
                "round_2_digest_artifact"
            ),
            "foundation_result": foundation_artifact,
            "brief_result": brief_artifact,
            "preview_result": preview_artifact,
            "approval_result": approval_resolution.get("approval_result"),
        },
        "artifact_refs": artifact_refs,
        "daily_factory": daily_factory_resolution.get("summary"),
        "editorial_meetings": editorial_meeting_resolution.get("summary"),
        "release_readiness": approval_resolution["release_readiness"],
        "hydrate_inputs": _derive_hydrate_inputs(
            workspace_id=workspace_id,
            daily_factory_resolution=daily_factory_resolution,
            editorial_meeting_resolution=editorial_meeting_resolution,
            foundation_artifact=foundation_artifact,
            brief_artifact=brief_artifact,
            preview_artifact=preview_artifact,
            approval_resolution=approval_resolution,
        ),
    }
