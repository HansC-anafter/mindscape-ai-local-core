"""
Dispatch policy gate for meeting engine action items.

Pre-dispatch checks validate playbook availability, tool allowlist,
workspace boundaries, and progressive contract enforcement. Failing
items are marked as ``policy_blocked`` with machine-readable metadata.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.models.execution_metadata import GOVERNANCE_PAYLOAD_FIELDS

logger = logging.getLogger(__name__)

AUTO_GATE_MODE = "auto"
VALID_GATE_MODES = {"auto", "warn", "block"}
RECOVERABLE_GOVERNANCE_FIELDS = {"trace_id"}
_INPUT_TEMPLATE_RE = re.compile(r"\{\{\s*input\.([a-zA-Z0-9_]+)\b")


def check_dispatch_policy(
    action_items: List[Dict[str, Any]],
    workspace_id: str,
    available_playbooks_cache: str = "",
    binding_store=None,
    *,
    manifest_cache: Optional[Dict[str, Any]] = None,
    workspace_data_sources: Optional[Dict[str, Any]] = None,
    contract_gate_mode: str = AUTO_GATE_MODE,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run policy checks on action items before dispatch.

    Mutates items in-place: sets ``landing_status='policy_blocked'``,
    ``landing_error``, ``policy_reason_code``, warning/block detail lists,
    and a ``policy_gate`` summary object on each item.

    Tool allowlist is resolved per-item using ``target_workspace_id``
    (falls back to session ``workspace_id``). Allowlists are cached
    per-workspace to avoid redundant store queries.

    Returns:
        Session-level machine-readable summary suitable for
        ``MeetingSession.metadata["policy_gate"]``.
    """
    requested_mode = _normalize_gate_mode(contract_gate_mode)
    request_contract = _extract_request_contract(session_metadata)

    report: Dict[str, Any] = {
        "requested_mode": requested_mode,
        "default_rollout": (
            "progressive" if requested_mode == AUTO_GATE_MODE else requested_mode
        ),
        "item_count": len(action_items),
        "blocked_count": 0,
        "warning_count": 0,
        "items": [],
    }

    # Build set of known playbook codes from the cache string
    known_playbook_codes = _parse_playbook_codes(available_playbooks_cache)
    if manifest_cache is None and known_playbook_codes:
        manifest_cache = _build_manifest_cache(known_playbook_codes)

    # Per-workspace allowlist cache (lazy-loaded)
    _allowlist_cache: Dict[str, Optional[set]] = {}
    _playbook_spec_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def _get_allowlist(ws_id: str) -> Optional[set]:
        if ws_id not in _allowlist_cache:
            _allowlist_cache[ws_id] = _load_tool_allowlist(ws_id, binding_store)
        return _allowlist_cache[ws_id]

    def _get_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
        if playbook_code not in _playbook_spec_cache:
            _playbook_spec_cache[playbook_code] = _load_playbook_spec(playbook_code)
        return _playbook_spec_cache[playbook_code]

    for item in action_items:
        playbook_code = item.get("playbook_code")
        tool_name = item.get("tool_name")
        manifest_entry = (
            manifest_cache.get(playbook_code)
            if playbook_code and isinstance(manifest_cache, dict)
            else None
        )
        playbook_spec = (
            _get_playbook_spec(playbook_code) if isinstance(playbook_code, str) else None
        )
        effective_mode, mode_source = _resolve_effective_gate_mode(
            requested_mode=requested_mode,
            manifest_entry=manifest_entry,
            playbook_spec=playbook_spec,
        )

        item_report: Dict[str, Any] = {
            "intent_id": item.get("intent_id"),
            "title": item.get("title"),
            "playbook_code": playbook_code,
            "tool_name": tool_name,
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "mode_source": mode_source,
            "warnings": [],
            "blocks": [],
            "auto_filled_governance_fields": [],
            "status": item.get("landing_status") or "allowed",
        }

        if item.get("landing_status"):
            item_report["status"] = item.get("landing_status")
            _update_item_policy_gate(item, item_report)
            report["items"].append(item_report)
            continue

        # Check 1: Unknown playbook
        if playbook_code and known_playbook_codes:
            if playbook_code not in known_playbook_codes:
                detail = _build_policy_detail(
                    reason_code="UNKNOWN_PLAYBOOK",
                    message=f"Playbook '{playbook_code}' not in installed playbooks",
                    playbook_code=playbook_code,
                )
                _apply_block(item, detail, item_report)
                report["blocked_count"] += 1
                report["items"].append(item_report)
                continue

        # Check 2: Tool allowlist (per target workspace)
        if tool_name and binding_store is not None:
            target_ws = item.get("target_workspace_id") or workspace_id
            allowed_tools = _get_allowlist(target_ws)
            if allowed_tools is not None:
                canonical_tool, candidates = _canonicalize_tool_name(
                    tool_name, allowed_tools
                )
                if canonical_tool is None:
                    suffix = ""
                    if candidates:
                        preview = ", ".join(sorted(candidates)[:5])
                        suffix = f" (ambiguous candidates: {preview})"
                    detail = _build_policy_detail(
                        reason_code="TOOL_NOT_ALLOWED",
                        message=(
                            f"Tool '{tool_name}' not in workspace '{target_ws}' "
                            f"allowlist{suffix}"
                        ),
                        tool_name=tool_name,
                        target_workspace_id=target_ws,
                        candidates=sorted(candidates),
                    )
                    _apply_block(item, detail, item_report)
                    report["blocked_count"] += 1
                    report["items"].append(item_report)
                    continue

                # Deterministic self-heal: normalize bare names to canonical
                # allowlist IDs before any LLM-based repair path.
                if canonical_tool != tool_name:
                    item["tool_name_original"] = tool_name
                    item["tool_name"] = canonical_tool
                    item["tool_name_normalized"] = True
                    item_report["tool_name"] = canonical_tool

            if allowed_tools is not None and item.get("tool_name") not in allowed_tools:
                detail = _build_policy_detail(
                    reason_code="TOOL_NOT_ALLOWED",
                    message=(
                        f"Tool '{item.get('tool_name')}' not in workspace "
                        f"'{target_ws}' allowlist"
                    ),
                    tool_name=item.get("tool_name"),
                    target_workspace_id=target_ws,
                )
                _apply_block(item, detail, item_report)
                report["blocked_count"] += 1
                report["items"].append(item_report)
                continue

        payload = _build_contract_payload(
            item=item,
            workspace_id=workspace_id,
            playbook_spec=playbook_spec,
            request_contract=request_contract,
        )

        warnings: List[Dict[str, Any]] = []
        blocking_findings: List[Dict[str, Any]] = []
        contract_findings = (
            blocking_findings if effective_mode == "block" else warnings
        )

        # Check 3: Contract input validation (consumes-vs-data_sources)
        if playbook_code and manifest_cache and workspace_data_sources is not None:
            required_types = _get_consumes_types(playbook_code, manifest_cache)
            if required_types:
                resolved_types = _get_available_types(workspace_data_sources)
                missing_types = required_types - resolved_types
                if missing_types:
                    detail = _build_policy_detail(
                        reason_code="CONTRACT_INPUT_MISMATCH",
                        message=(
                            f"Playbook '{playbook_code}' requires types "
                            f"{sorted(missing_types)} not found in workspace"
                        ),
                        playbook_code=playbook_code,
                        required_types=sorted(required_types),
                        resolved_types=sorted(resolved_types),
                        missing_types=sorted(missing_types),
                    )
                    contract_findings.append(detail)

        # Check 4: Structured payload required fields
        if playbook_code and playbook_spec:
            missing_required_fields = _get_missing_required_inputs(
                playbook_spec=playbook_spec,
                payload=payload,
            )
            if missing_required_fields:
                detail = _build_policy_detail(
                    reason_code="REQUIRED_INPUT_MISSING",
                    message=(
                        f"Playbook '{playbook_code}' missing required inputs "
                        f"{missing_required_fields}"
                    ),
                    playbook_code=playbook_code,
                    missing_fields=missing_required_fields,
                    payload_keys=sorted(payload.keys()),
                )
                contract_findings.append(detail)

            missing_governance_fields, recoverable_governance_fields = (
                _get_governance_validation(playbook_spec=playbook_spec, payload=payload)
            )
            if recoverable_governance_fields:
                item_report["auto_filled_governance_fields"] = (
                    recoverable_governance_fields
                )

            if missing_governance_fields:
                detail = _build_policy_detail(
                    reason_code="GOVERNANCE_FIELD_MISSING",
                    message=(
                        f"Playbook '{playbook_code}' missing governance fields "
                        f"{missing_governance_fields}"
                    ),
                    playbook_code=playbook_code,
                    missing_governance_fields=missing_governance_fields,
                    payload_keys=sorted(payload.keys()),
                )
                contract_findings.append(detail)

        for warning in warnings:
            _add_warning(item, warning, item_report)

        if blocking_findings:
            for detail in blocking_findings:
                _add_block_detail(item, detail, item_report)
            primary = blocking_findings[0]
            _mark_blocked(
                item,
                reason_code=primary["reason_code"],
                message=primary["message"],
            )
            item_report["status"] = item.get("landing_status") or "policy_blocked"
            report["blocked_count"] += 1
        else:
            if warnings:
                item_report["status"] = "warning"
                report["warning_count"] += len(warnings)
            else:
                item_report["status"] = "allowed"

        _update_item_policy_gate(item, item_report)
        report["items"].append(item_report)

    return report


def _mark_blocked(
    item: Dict[str, Any],
    reason_code: str,
    message: str,
) -> None:
    """Mark an action item as policy-blocked."""
    item["landing_status"] = "policy_blocked"
    item["landing_error"] = message
    item["policy_reason_code"] = reason_code
    logger.info(
        "Policy gate blocked item '%s': %s (%s)",
        item.get("title"),
        message,
        reason_code,
    )


def _apply_block(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Apply an unconditional block finding to item and report."""
    _add_block_detail(item, detail, item_report)
    _mark_blocked(
        item,
        reason_code=detail["reason_code"],
        message=detail["message"],
    )
    item_report["status"] = item.get("landing_status") or "policy_blocked"
    _update_item_policy_gate(item, item_report)


def _add_warning(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Attach a machine-readable warning to item and report."""
    warning = dict(detail)
    warning["policy_warning_code"] = warning["reason_code"]
    warnings = item.setdefault("policy_warnings", [])
    warnings.append(warning)
    item["policy_warning"] = warnings[0]
    item_report["warnings"].append(warning)
    logger.info(
        "Policy gate warning on item '%s': %s (%s)",
        item.get("title"),
        warning["message"],
        warning["reason_code"],
    )


def _add_block_detail(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Attach a machine-readable block detail to item and report."""
    block = dict(detail)
    block["policy_reason_code"] = block["reason_code"]
    item.setdefault("policy_blocks", []).append(block)
    item_report["blocks"].append(block)


def _update_item_policy_gate(
    item: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Write normalized policy gate metadata back to action item."""
    item["policy_gate"] = {
        "requested_mode": item_report["requested_mode"],
        "effective_mode": item_report["effective_mode"],
        "mode_source": item_report["mode_source"],
        "status": item_report["status"],
        "warnings": list(item_report["warnings"]),
        "blocks": list(item_report["blocks"]),
        "auto_filled_governance_fields": list(
            item_report.get("auto_filled_governance_fields", [])
        ),
    }


def _build_policy_detail(
    *,
    reason_code: str,
    message: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Create a normalized machine-readable policy finding payload."""
    detail = {
        "reason_code": reason_code,
        "message": message,
    }
    detail.update(extra)
    return detail


def _normalize_gate_mode(mode: Optional[str]) -> str:
    """Normalize gate mode, falling back to progressive auto mode."""
    normalized = (mode or AUTO_GATE_MODE).strip().lower()
    if normalized in VALID_GATE_MODES:
        return normalized
    logger.warning("Unknown contract_gate_mode '%s', falling back to auto", mode)
    return AUTO_GATE_MODE


def _resolve_effective_gate_mode(
    *,
    requested_mode: str,
    manifest_entry: Optional[Dict[str, Any]],
    playbook_spec: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    """Resolve the per-playbook effective gate mode."""
    if requested_mode == "block":
        return "block", "forced_block"
    if requested_mode == "warn":
        return "warn", "forced_warn"

    manifest_mode = _resolve_manifest_gate_override(manifest_entry)
    if manifest_mode == "block":
        return "block", "manifest_opt_in"
    if manifest_mode == "warn":
        return "warn", "manifest_override"
    if playbook_spec:
        return "block", "structured_playbook_spec"
    return "warn", "legacy_manifest"


def _resolve_manifest_gate_override(
    manifest_entry: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Read explicit contract gate opt-ins from manifest metadata if present."""
    if not isinstance(manifest_entry, dict):
        return None

    def _nested_get(data: Dict[str, Any], *path: str) -> Any:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    mode_candidates = (
        ("contract_gate_mode",),
        ("policy", "contract_gate_mode"),
        ("dispatch_policy", "contract_gate_mode"),
        ("governance", "contract_gate_mode"),
    )
    for path in mode_candidates:
        value = _nested_get(manifest_entry, *path)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"warn", "block"}:
                return normalized

    opt_in_candidates = (
        ("contract_gate_opt_in",),
        ("policy", "contract_gate_opt_in"),
        ("dispatch_policy", "contract_gate_opt_in"),
        ("governance", "contract_gate_opt_in"),
    )
    for path in opt_in_candidates:
        if _nested_get(manifest_entry, *path) is True:
            return "block"

    return None


def _build_contract_payload(
    *,
    item: Dict[str, Any],
    workspace_id: str,
    playbook_spec: Optional[Dict[str, Any]],
    request_contract: Optional[Dict[str, Any]],
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

    for gov_field in GOVERNANCE_PAYLOAD_FIELDS:
        if gov_field in item and item[gov_field] is not None and gov_field not in payload:
            payload[gov_field] = item[gov_field]

    if request_contract:
        if (
            "acceptance_tests" not in payload
            and request_contract.get("acceptance_tests") is not None
        ):
            payload["acceptance_tests"] = request_contract["acceptance_tests"]
        if (
            "governance_constraints" not in payload
            and request_contract.get("constraints") is not None
        ):
            payload["governance_constraints"] = request_contract["constraints"]

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


def _load_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
    """Load structured playbook spec from playbook.json if available."""
    try:
        from backend.app.services.playbook_loaders import PlaybookJsonLoader

        playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
        if playbook_json is None:
            return None
        if hasattr(playbook_json, "model_dump"):
            return playbook_json.model_dump(exclude_none=True)
        return None
    except Exception as exc:
        logger.debug("Failed to load playbook.json for %s: %s", playbook_code, exc)
        return None


def _parse_playbook_codes(cache_str: str) -> set:
    """Extract playbook codes from the formatted cache string.

    Cache format is lines like '- playbook_code: Playbook Name'.
    Returns empty set if cache is empty or unparseable.
    """
    codes = set()
    if not cache_str:
        return codes
    for line in cache_str.strip().split("\n"):
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            code_part = line[2:].split(":", 1)[0].strip()
            if code_part:
                codes.add(code_part)
    return codes


def _load_tool_allowlist(
    workspace_id: str,
    binding_store=None,
) -> Optional[set]:
    """Load allowed tool names from workspace resource bindings.

    Returns:
        Set of allowed tool names, or None if no binding_store
        (which means tool allowlist is not enforced).
    """
    if binding_store is None:
        return None
    try:
        from backend.app.models.workspace_resource_binding import ResourceType

        bindings = binding_store.list_bindings_by_workspace(
            workspace_id, resource_type=ResourceType.TOOL
        )
        if not bindings:
            return None  # fail-open: no TOOL bindings = no restriction
        return {b.resource_id for b in bindings}
    except Exception as exc:
        logger.warning("Failed to load tool allowlist for %s: %s", workspace_id, exc)
        return None


def _build_manifest_cache(playbook_codes: Set[str]) -> Dict[str, Any]:
    """Build a minimal playbook manifest cache from affordance declarations."""
    try:
        from backend.app.services.manifest_utils import resolve_playbook_affordance

        manifest_cache: Dict[str, Any] = {}
        for playbook_code in playbook_codes:
            affordance = resolve_playbook_affordance(playbook_code)
            if affordance:
                manifest_cache[playbook_code] = affordance
        return manifest_cache
    except Exception as exc:
        logger.debug("Failed to build manifest cache for policy gate: %s", exc)
        return {}


def _get_consumes_types(
    playbook_code: str,
    manifest_cache: Dict[str, Any],
) -> Set[str]:
    """Extract required consumes types for a playbook from manifest cache.

    Supports both bare-string and dict-form consumes entries.
    Returns empty set if playbook not found or has no consumes.
    """
    pb_entry = manifest_cache.get(playbook_code)
    if not isinstance(pb_entry, dict):
        return set()
    consumes = pb_entry.get("consumes") or []
    return {
        (c.get("type", "") if isinstance(c, dict) else c)
        for c in consumes
        if c
    }


def _get_available_types(
    workspace_data_sources: Dict[str, Any],
) -> Set[str]:
    """Extract available asset types from workspace data_sources.

    data_sources format: {pack_id: {produces: [{type: ...}, ...]}}.
    """
    types: Set[str] = set()
    for _pack_id, pack_data in workspace_data_sources.items():
        if isinstance(pack_data, dict):
            for prod in pack_data.get("produces", []):
                if isinstance(prod, dict) and prod.get("type"):
                    types.add(prod["type"])
    return types


def _canonicalize_tool_name(
    tool_name: Any,
    allowed_tools: Set[str],
) -> Tuple[Optional[str], List[str]]:
    """Return canonical tool name from allowlist, if resolvable.

    Resolution order:
    1. Exact match
    2. Unique suffix match (e.g., ig_fetch_posts -> ig.ig_fetch_posts)

    Returns:
        (canonical_name, candidates)
        - canonical_name: resolved allowlist entry, or None if not resolvable.
        - candidates: suffix candidates (for ambiguity diagnostics).
    """
    if not isinstance(tool_name, str):
        return None, []
    name = tool_name.strip()
    if not name:
        return None, []
    if name in allowed_tools:
        return name, []

    suffix = name.rsplit(".", 1)[-1]
    candidates = [
        allowed for allowed in allowed_tools if allowed.rsplit(".", 1)[-1] == suffix
    ]
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates
