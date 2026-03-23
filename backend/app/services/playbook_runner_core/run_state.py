"""Run-state event builders extracted from ``playbook_runner.py``."""

import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.execution_core.clock import utc_now

IG_PLAYBOOK_REFRESH_HINTS = {
    "ig_analyze_following": ["sources", "targets", "run_logs"],
    "ig_capture_account_snapshot": ["captures", "run_logs"],
    "ig_analyze_pinned_reference": ["references", "run_logs"],
    "ig_batch_pin_references": ["references", "run_logs"],
}


def normalize_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_optional_handle(value: Any) -> Optional[str]:
    text = normalize_optional_text(value)
    if not text:
        return None
    return text[1:] if text.startswith("@") else text


def derive_pack_id(playbook_code: str) -> Optional[str]:
    if isinstance(playbook_code, str) and playbook_code.startswith("ig_"):
        return "ig"
    return None


def derive_refresh_hint(playbook_code: str) -> List[str]:
    if not isinstance(playbook_code, str):
        return []
    if playbook_code in IG_PLAYBOOK_REFRESH_HINTS:
        return list(IG_PLAYBOOK_REFRESH_HINTS[playbook_code])
    if playbook_code.startswith("ig_"):
        return ["run_logs"]
    return []


def derive_ui_surface(refresh_hint: List[str]) -> str:
    if "references" in refresh_hint:
        return "references"
    if any(hint in {"sources", "targets", "captures"} for hint in refresh_hint):
        return "discovery"
    return "workbench"


def build_run_state_context(
    playbook_code: str,
    execution_id: str,
    new_state: str,
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = inputs if isinstance(inputs, dict) else {}
    refresh_hint = derive_refresh_hint(playbook_code)
    target_username = normalize_optional_handle(
        ctx.get("target_username") or ctx.get("target_handle")
    )
    reference_id = normalize_optional_text(ctx.get("reference_id") or ctx.get("ref_id"))
    user_data_dir = normalize_optional_text(ctx.get("user_data_dir"))
    terminal = new_state in {"DONE", "FAILED", "CANCELLED"}
    pack_id = derive_pack_id(playbook_code)

    return {
        "pack_id": pack_id,
        "execution_id": execution_id,
        "lifecycle_state": new_state,
        "terminal": terminal,
        "ui_surface": derive_ui_surface(refresh_hint),
        "refresh_hint": refresh_hint,
        "target_username": target_username,
        "target_handle": target_username,
        "reference_id": reference_id,
        "user_data_dir": user_data_dir,
    }


def build_run_state_payload(
    previous_state: str,
    new_state: str,
    reason: str,
    playbook_code: str,
    execution_id: str,
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "execution_id": execution_id,
        "previous_state": previous_state,
        "new_state": new_state,
        "reason": reason,
        "playbook_code": playbook_code,
        "blocker_count": 0,
    }

    ctx = build_run_state_context(playbook_code, execution_id, new_state, inputs)
    for key in (
        "pack_id",
        "lifecycle_state",
        "terminal",
        "refresh_hint",
        "target_username",
        "target_handle",
        "reference_id",
        "user_data_dir",
        "ui_surface",
    ):
        value = ctx.get(key)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        payload[key] = value
    return payload


def build_run_state_metadata(
    playbook_code: str,
    execution_id: str,
    new_state: str,
    reason: str,
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = {
        "playbook_code": playbook_code,
        "reason": reason,
    }
    for key, value in build_run_state_context(
        playbook_code, execution_id, new_state, inputs
    ).items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        metadata[key] = value
    return metadata


def build_run_state_changed_event(
    *,
    profile_id: str,
    project_id: Optional[str],
    workspace_id: Optional[str],
    execution_id: str,
    previous_state: str,
    new_state: str,
    reason: str,
    playbook_code: str,
    inputs: Optional[Dict[str, Any]] = None,
) -> MindEvent:
    return MindEvent(
        id=str(uuid.uuid4()),
        timestamp=utc_now(),
        actor=EventActor.AGENT,
        channel="playbook",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        event_type=EventType.RUN_STATE_CHANGED,
        payload=build_run_state_payload(
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            playbook_code=playbook_code,
            execution_id=execution_id,
            inputs=inputs,
        ),
        entity_ids=[execution_id] if execution_id else [],
        metadata=build_run_state_metadata(
            playbook_code=playbook_code,
            execution_id=execution_id,
            new_state=new_state,
            reason=reason,
            inputs=inputs,
        ),
    )
