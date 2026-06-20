"""Lifecycle operations for visual acceptance follow-up requests."""

from typing import Any, Dict, List, Optional

from .artifacts import (
    get_visual_acceptance_artifacts_store,
    _list_workspace_artifacts,
    _upsert_request_artifact,
)
from .constants import (
    FOLLOWUP_REQUEST_STATE_BLOCKED,
    VALID_FOLLOWUP_REQUEST_STATES,
    VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
)
from .dependencies import (
    Artifact,
    normalize_followup_action_id,
    normalize_followup_consumer_kind,
    normalize_followup_lane_id,
)
from .identifiers import _utc_now_iso
from .request_payloads import _request_payload
from .state_sync import (
    _sync_followup_request_state_to_bundle,
    _sync_followup_request_state_to_run,
)


def materialize_followup_request_artifacts(
    *,
    bundle: Dict[str, Any],
    decision_payload: Dict[str, Any],
    artifacts_store: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    workspace_id = str(bundle.get("workspace_id") or "").strip()
    review_bundle_id = str(bundle.get("review_bundle_id") or "").strip()
    lanes = [
        {
            **dict(item),
            "lane_id": normalize_followup_lane_id(item.get("lane_id")),
            "consumer_kind": normalize_followup_consumer_kind(item.get("consumer_kind")),
            "action_ids": [
                normalize_followup_action_id(action_id)
                for action_id in (item.get("action_ids") or [])
                if normalize_followup_action_id(action_id)
            ],
        }
        for item in ((decision_payload.get("downstream_action_plan") or {}).get("lanes") or [])
        if isinstance(item, dict)
    ]
    if not workspace_id or not review_bundle_id:
        return []

    store = artifacts_store or get_visual_acceptance_artifacts_store()
    active_lane_ids = {
        normalize_followup_lane_id(item.get("lane_id"))
        for item in lanes
        if normalize_followup_lane_id(item.get("lane_id"))
    }

    refs: List[Dict[str, Any]] = []
    for lane in lanes:
        payload = _request_payload(
            bundle=bundle,
            decision_payload=decision_payload,
            lane=lane,
        )
        refs.append(
            _upsert_request_artifact(
                workspace_id=workspace_id,
                payload=payload,
                artifacts_store=store,
            )
        )

    for artifact in _list_workspace_artifacts(workspace_id=workspace_id, artifacts_store=store):
        metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
        if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
            continue
        if str(metadata.get("review_bundle_id") or "").strip() != review_bundle_id:
            continue
        lane_id = normalize_followup_lane_id(metadata.get("lane_id"))
        if not lane_id or lane_id in active_lane_ids:
            continue
        payload = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
        payload["request_state"] = "superseded"
        payload["blocking_reason"] = "review_decision_replaced"
        metadata["request_state"] = "superseded"
        metadata["blocking_reason"] = "review_decision_replaced"
        store.update_artifact(
            artifact.id,
            content=payload,
            metadata=metadata,
        )

    return refs


def persist_followup_request_state(
    *,
    artifact: Artifact,
    request_state: str,
    actor_id: str = "",
    notes: str = "",
    execution_ref: Optional[Dict[str, Any]] = None,
    artifacts_store: Optional[Any] = None,
) -> Artifact:
    normalized_state = str(request_state or "").strip().lower()
    if normalized_state not in VALID_FOLLOWUP_REQUEST_STATES:
        raise ValueError(f"invalid_followup_request_state:{request_state}")
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
        raise ValueError("artifact_not_visual_acceptance_followup_request")

    content = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
    content["lane_id"] = normalize_followup_lane_id(content.get("lane_id")) or None
    content["consumer_kind"] = (
        normalize_followup_consumer_kind(content.get("consumer_kind")) or None
    )
    content["action_ids"] = [
        normalize_followup_action_id(action_id)
        for action_id in (content.get("action_ids") or [])
        if normalize_followup_action_id(action_id)
    ]
    metadata["lane_id"] = normalize_followup_lane_id(metadata.get("lane_id")) or None
    metadata["consumer_kind"] = (
        normalize_followup_consumer_kind(metadata.get("consumer_kind")) or None
    )
    transition_event = {
        "request_state": normalized_state,
        "actor_id": str(actor_id or "").strip() or None,
        "notes": str(notes or "").strip() or None,
        "execution_ref": dict(execution_ref or {}),
        "handled_at": _utc_now_iso(),
    }
    history = [
        dict(item)
        for item in (content.get("request_events") or [])
        if isinstance(item, dict)
    ]
    history.append(transition_event)
    content["request_state"] = normalized_state
    content["blocking_reason"] = (
        content.get("blocking_reason")
        if normalized_state == FOLLOWUP_REQUEST_STATE_BLOCKED
        else None
    )
    content["request_events"] = history
    content["last_transition"] = transition_event
    metadata["request_state"] = normalized_state
    metadata["last_transition"] = transition_event
    if transition_event["actor_id"]:
        metadata["last_actor_id"] = transition_event["actor_id"]

    store = artifacts_store or get_visual_acceptance_artifacts_store()
    store.update_artifact(
        artifact.id,
        content=content,
        metadata=metadata,
    )
    updated_artifact = store.get_artifact(artifact.id)
    final_artifact = updated_artifact or artifact.model_copy(update={"content": content, "metadata": metadata})
    _sync_followup_request_state_to_bundle(
        request_artifact=final_artifact,
        request_content=content,
        transition_event=transition_event,
        artifacts_store=store,
    )
    _sync_followup_request_state_to_run(
        request_artifact=final_artifact,
        request_content=content,
        transition_event=transition_event,
    )
    refreshed = store.get_artifact(final_artifact.id)
    return refreshed or final_artifact
