"""
Handoff models for cross-boundary task delegation.

Defines HandoffIn (upstream request) and Commitment (downstream response)
for structured agent-to-agent task handoffs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _clean_string_list(values: Any) -> List[str]:
    cleaned: List[str] = []
    if not isinstance(values, list):
        return cleaned
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _normalize_pd_storyboard_seed(seed: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for field_name in (
        "session_id",
        "workspace_id",
        "project_id",
        "reference_id",
        "source_type",
        "character_binding_mode",
        "performance_mode",
    ):
        value = seed.get(field_name)
        if isinstance(value, str) and value.strip():
            normalized[field_name] = value.strip()
    for field_name in (
        "intent",
        "scene_package_selector",
        "spatial_schedule",
        "render_profile",
        "global_settings",
        "workload_execution_intent",
        "capture_bundle",
        "provider_payload",
        "motion_provider_payload",
    ):
        value = seed.get(field_name)
        if isinstance(value, dict) and value:
            normalized[field_name] = value
    for field_name in (
        "cast",
        "scene_specs",
        "character_package_refs",
        "performance_package_refs",
        "speaker_audio_refs",
        "driving_clip_refs",
        "source_reference_ids",
    ):
        value = seed.get(field_name)
        if isinstance(value, list) and value:
            normalized[field_name] = value
    for field_name in (
        "require_retargetable_performance_replay",
        "auto_advance",
    ):
        value = seed.get(field_name)
        if isinstance(value, bool):
            normalized[field_name] = value
    for field_name in ("advance_limit", "motion_seed"):
        value = seed.get(field_name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized[field_name] = value
    return normalized


def _extract_pd_storyboard_seed(values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    direct_seed = values.get("pd_storyboard_seed")
    if isinstance(direct_seed, dict) and direct_seed:
        return _normalize_pd_storyboard_seed(direct_seed)

    governance_constraints = values.get("governance_constraints")
    if isinstance(governance_constraints, dict):
        seeded = governance_constraints.get("pd_storyboard_seed")
        if isinstance(seeded, dict) and seeded:
            return _normalize_pd_storyboard_seed(seeded)

    constraints = values.get("constraints")
    if isinstance(constraints, dict):
        seeded = constraints.get("pd_storyboard_seed")
        if isinstance(seeded, dict) and seeded:
            return _normalize_pd_storyboard_seed(seeded)

    attachments = values.get("context_attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            typed_marker = str(
                attachment.get("type")
                or attachment.get("kind")
                or attachment.get("name")
                or attachment.get("attachment_type")
                or ""
            ).strip()
            payload = attachment.get("payload")
            if typed_marker == "pd_storyboard_seed" and isinstance(payload, dict):
                return _normalize_pd_storyboard_seed(payload)
            nested_seed = attachment.get("pd_storyboard_seed")
            if isinstance(nested_seed, dict) and nested_seed:
                return _normalize_pd_storyboard_seed(nested_seed)
    return None


def _select_pd_storyboard_route(seed: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(seed, dict) or not seed:
        return None
    if seed.get("scene_package_selector") and seed.get("session_id"):
        return "pd_scene_package_preview_handoff"
    if seed.get("session_id"):
        return "pd_execute_storyboard_preview"
    if seed.get("reference_id") and isinstance(seed.get("intent"), dict):
        return "pd_intake_storyboard_preview"
    return None


def _build_pd_storyboard_playbook_request(values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    seed = _extract_pd_storyboard_seed(values)
    route = _select_pd_storyboard_route(seed)
    if not seed or not route:
        return None

    workspace_id = str(seed.get("workspace_id") or values.get("workspace_id") or "").strip()
    if not workspace_id:
        return None
    project_id = str(seed.get("project_id") or "").strip() or None

    input_params: Dict[str, Any] = {"workspace_id": workspace_id}
    if project_id:
        input_params["project_id"] = project_id

    for field_name in (
        "source_type",
        "scene_specs",
        "spatial_schedule",
        "character_binding_mode",
        "character_package_refs",
        "performance_mode",
        "performance_package_refs",
        "speaker_audio_refs",
        "driving_clip_refs",
        "require_retargetable_performance_replay",
        "render_profile",
        "global_settings",
        "workload_execution_intent",
    ):
        if seed.get(field_name) not in (None, "", [], {}):
            input_params[field_name] = seed[field_name]

    if route == "pd_scene_package_preview_handoff":
        selector = seed.get("scene_package_selector") or {}
        if seed.get("session_id"):
            input_params["session_id"] = seed["session_id"]
        for selector_field, target_field in (
            ("provider", "provider_code"),
            ("generation_mode", "generation_mode"),
            ("scene_scope", "scene_scope"),
            ("variant_id", "variant_id"),
        ):
            selector_value = str(selector.get(selector_field) or "").strip()
            if selector_value:
                input_params[target_field] = selector_value
        for passthrough_field in (
            "source_reference_ids",
            "capture_bundle",
            "provider_payload",
            "motion_provider_payload",
            "motion_seed",
            "auto_advance",
            "advance_limit",
        ):
            if seed.get(passthrough_field) not in (None, "", [], {}):
                input_params[passthrough_field] = seed[passthrough_field]
        title = "Run scene-package storyboard preview handoff"
        description = (
            "Use the provided PD session and scene-package selector to resolve "
            "a replayable storyboard preview path, then execute the MMS preview "
            "lane when the selector is ready."
        )
    elif route == "pd_execute_storyboard_preview":
        input_params["session_id"] = seed.get("session_id")
        if seed.get("scene_package_selector"):
            input_params["scene_package_selector"] = seed["scene_package_selector"]
        title = "Execute storyboard preview from PD session"
        description = (
            "Use the existing PD session to generate a storyboard manifest and "
            "execute it through the MMS preview lane."
        )
    else:
        input_params["reference_id"] = seed.get("reference_id")
        input_params["intent"] = seed.get("intent")
        if seed.get("cast"):
            input_params["cast"] = seed["cast"]
        title = "Create PD session and execute storyboard preview"
        description = (
            "Create a PD session from the provided reference and intent seed, "
            "generate a storyboard manifest, and execute it through MMS."
        )

    return {
        "title": title,
        "description": description,
        "playbook_code": route,
        "engine": f"playbook:{route}",
        "priority": "high",
        "intent_id": f"PB_{route}",
        "input_params": input_params,
        "replace_existing_playbook_codes": [
            "pd_execute_storyboard_preview",
            "pd_intake_storyboard_preview",
            "pd_scene_package_preview_handoff",
            "pd_storyboard_gen",
        ],
        "preserve_atomic_playbook": True,
        "target_workspace_id": workspace_id,
        "handled_deliverable_ids": _clean_string_list(values.get("deliverable_ids")),
        "request_contract_source": "handoff_pd_storyboard_seed",
    }


class DeliverableSpec(BaseModel):
    """Typed output specification for a handoff."""

    name: str
    mime_type: str
    description: Optional[str] = None


class HandoffConstraints(BaseModel):
    """Execution constraints for a handoff."""

    style_refs: Optional[List[str]] = None
    ip_policy: Optional[str] = None
    action_space: Optional[str] = Field(
        None,
        description="Allowed side-effect level: READ_ONLY / WRITE_WS / NETWORK_CALL / PUBLISH / BILLING / DESTRUCTIVE",
    )
    max_duration_seconds: Optional[int] = None


class HandoffIn(BaseModel):
    """Cross-boundary handoff request from upstream to downstream (A -> B).

    Represents the contract that entity A sends to entity B,
    specifying what needs to be done, with what constraints,
    and how to validate completion.
    """

    handoff_id: str
    workspace_id: str
    intent_summary: str = Field(..., description="What the task is about")
    goals: List[str] = Field(
        default_factory=list, description="Explicit deliverable goals"
    )
    non_goals: Optional[List[str]] = None
    deliverables: List[DeliverableSpec] = Field(default_factory=list)
    constraints: Optional[HandoffConstraints] = None
    acceptance_tests: Optional[List[str]] = None  # Deprecated: use GovernanceContext.acceptance_tests
    risk_notes: Optional[List[str]] = None

    # Optional governance transport fields.
    trace_id: Optional[str] = Field(None, description="End-to-end trace identifier")
    governance_constraints: Optional[Dict[str, Any]] = Field(
        None, description="Typed governance constraints for downstream engines"
    )
    requested_output_type: Optional[str] = Field(
        None, description="Expected output MIME type (e.g. text/markdown)"
    )
    human_instructions: Optional[str] = Field(
        None, description="Free-form human instructions for the pack"
    )
    playbook_requests: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "Deterministic downstream playbook requests. Each entry can declare "
            "playbook_code, input_params, handled_deliverable_ids, and atomic "
            "dispatch hints without hard-coding pack rules into meeting core."
        ),
    )
    playbook_input_defaults: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "Generic input bootstrap rules for downstream playbooks. Each entry "
            "can target a playbook_code and optional deliverable_ids, then "
            "provide input_params defaults for meeting to merge without "
            "hard-coding pack-specific bootstrap logic."
        ),
    )
    context_attachments: Optional[List[Dict[str, Any]]] = Field(
        None, description="Evidence / provenance attachments passed to downstream"
    )
    deadline: Optional[datetime] = None
    assets: List[str] = Field(
        default_factory=list, description="Input artifact references"
    )
    source_device_id: Optional[str] = None
    target_device_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    @model_validator(mode="before")
    @classmethod
    def _normalize_transport_contract(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        if values.get("playbook_requests") is not None:
            return values

        derived_request = _build_pd_storyboard_playbook_request(values)
        if derived_request:
            values = dict(values)
            values["playbook_requests"] = [derived_request]
        return values


class Commitment(BaseModel):
    """Downstream commitment response to a HandoffIn (B -> A).

    Represents entity B's acceptance or rejection of the handoff,
    along with scope negotiation details.
    """

    commitment_id: str
    handoff_id: str = Field(..., description="References the originating HandoffIn")
    accepted: bool
    scope_summary: str
    open_questions: Optional[List[str]] = None
    estimated_phases: Optional[int] = None
    estimated_duration_seconds: Optional[int] = None
    task_ir_id: Optional[str] = Field(
        None, description="References compiled TaskIR if accepted"
    )
    created_at: datetime = Field(default_factory=_utc_now)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
