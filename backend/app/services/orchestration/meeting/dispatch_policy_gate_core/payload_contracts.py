"""Dispatch policy payload contract validation helpers."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.models.execution_metadata import GOVERNANCE_PAYLOAD_FIELDS

RECOVERABLE_GOVERNANCE_FIELDS = {"trace_id"}
_INPUT_TEMPLATE_RE = re.compile(r"\{\{\s*input\.([a-zA-Z0-9_]+)\b")


def _build_contract_payload(
    *,
    item: Dict[str, Any],
    workspace_id: str,
    playbook_spec: Optional[Dict[str, Any]],
    request_contract: Optional[Dict[str, Any]],
    meeting_session_id: Optional[str],
    project_id: Optional[str],
) -> Dict[str, Any]:
    """Build the effective payload shape seen by contract validation."""
    payload = {}

    raw_params = item.get("input_params")
    if isinstance(raw_params, dict):
        payload.update(raw_params)

    if playbook_spec:
        spec_inputs = playbook_spec.get("inputs", {})
        if isinstance(spec_inputs, dict):
            for field_name in spec_inputs.keys():
                if field_name not in payload and item.get(field_name) is not None:
                    payload[field_name] = item[field_name]

    resolved_workspace_id = item.get("target_workspace_id") or workspace_id
    if resolved_workspace_id and "workspace_id" not in payload:
        payload["workspace_id"] = resolved_workspace_id
    if meeting_session_id and "meeting_session_id" not in payload:
        payload["meeting_session_id"] = meeting_session_id
    if project_id and "project_id" not in payload:
        payload["project_id"] = project_id

    for gov_field in GOVERNANCE_PAYLOAD_FIELDS:
        if gov_field in item and item[gov_field] is not None and gov_field not in payload:
            payload[gov_field] = item[gov_field]

    if request_contract:
        for gov_field in GOVERNANCE_PAYLOAD_FIELDS:
            if gov_field in payload:
                continue
            if gov_field == "governance_constraints":
                candidate = request_contract.get(
                    "governance_constraints"
                ) or request_contract.get("constraints")
            else:
                candidate = request_contract.get(gov_field)
            if candidate is not None:
                payload[gov_field] = candidate

    return payload


def _extract_request_contract(
    session_metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Read request contract dict from meeting session metadata."""
    if not isinstance(session_metadata, dict):
        return None
    request_contract = session_metadata.get("request_contract")
    return request_contract if isinstance(request_contract, dict) else None


def _has_payload_value(payload: Dict[str, Any], field_name: str) -> bool:
    """Return whether payload contains a materially present value."""
    if field_name not in payload:
        return False
    value = payload.get(field_name)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _get_missing_required_inputs(
    *,
    playbook_spec: Dict[str, Any],
    payload: Dict[str, Any],
) -> List[str]:
    """Return structured-spec required inputs still missing after fallbacks."""
    missing: List[str] = []
    spec_inputs = playbook_spec.get("inputs", {})
    if not isinstance(spec_inputs, dict):
        return missing

    for field_name, field_def in spec_inputs.items():
        if field_name in GOVERNANCE_PAYLOAD_FIELDS:
            continue
        if not isinstance(field_def, dict):
            continue
        if not field_def.get("required", True):
            continue
        if field_def.get("default") is not None:
            continue
        if not _has_payload_value(payload, field_name):
            missing.append(field_name)
    return sorted(missing)


def _get_governance_validation(
    *,
    playbook_spec: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    """Return (missing, recoverable) governance fields required by playbook."""
    required_fields = _get_required_governance_fields(playbook_spec)
    missing: List[str] = []
    recoverable: List[str] = []
    for field_name in required_fields:
        if _has_payload_value(payload, field_name):
            continue
        if field_name in RECOVERABLE_GOVERNANCE_FIELDS:
            recoverable.append(field_name)
        else:
            missing.append(field_name)
    return sorted(missing), sorted(recoverable)


def _get_required_governance_fields(playbook_spec: Dict[str, Any]) -> Set[str]:
    """Infer governance fields required by structured playbook contract."""
    required: Set[str] = set()
    spec_inputs = playbook_spec.get("inputs", {})
    if isinstance(spec_inputs, dict):
        for field_name in GOVERNANCE_PAYLOAD_FIELDS:
            field_def = spec_inputs.get(field_name)
            if not isinstance(field_def, dict):
                continue
            if field_def.get("required", True) and field_def.get("default") is None:
                required.add(field_name)

    referenced_inputs = _find_input_template_references(playbook_spec)
    if isinstance(spec_inputs, dict):
        for field_name in GOVERNANCE_PAYLOAD_FIELDS:
            if field_name not in referenced_inputs:
                continue
            field_def = spec_inputs.get(field_name)
            if isinstance(field_def, dict):
                if field_def.get("default") is not None:
                    continue
                if field_def.get("required") is False:
                    continue
            required.add(field_name)

    return required


def _find_input_template_references(playbook_spec: Dict[str, Any]) -> Set[str]:
    """Find all ``{{input.xxx}}`` references in structured playbook spec."""
    found: Set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _walk(value)
            return
        if isinstance(node, list):
            for value in node:
                _walk(value)
            return
        if isinstance(node, str):
            found.update(match.group(1) for match in _INPUT_TEMPLATE_RE.finditer(node))

    _walk(playbook_spec.get("steps") or [])
    _walk(playbook_spec.get("lifecycle_hooks") or {})
    return found
