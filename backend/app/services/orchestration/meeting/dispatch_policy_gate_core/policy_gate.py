"""Dispatch policy gate orchestration."""

import sys
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting.dispatch_policy_gate_core import (
    manifest_sources,
)
from backend.app.services.orchestration.meeting.dispatch_policy_gate_core.findings import (
    _add_block_detail,
    _add_warning,
    _apply_block,
    _build_policy_detail,
    _mark_blocked,
    _update_item_policy_gate,
)
from backend.app.services.orchestration.meeting.dispatch_policy_gate_core.gate_mode import (
    AUTO_GATE_MODE,
    _normalize_gate_mode,
    _resolve_effective_gate_mode,
)
from backend.app.services.orchestration.meeting.dispatch_policy_gate_core.payload_contracts import (
    _build_contract_payload,
    _extract_request_contract,
    _get_governance_validation,
    _get_missing_required_inputs,
)

_COMPAT_MODULE = "backend.app.services.orchestration.meeting.dispatch_policy_gate"


def _manifest_helper(name: str):
    module = sys.modules.get(_COMPAT_MODULE)
    if module is not None:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    return getattr(manifest_sources, name)


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
    meeting_session_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run policy checks on action items before dispatch."""
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

    known_playbook_codes = _manifest_helper("_parse_playbook_codes")(
        available_playbooks_cache
    )
    if manifest_cache is None and known_playbook_codes:
        manifest_cache = _manifest_helper("_build_manifest_cache")(known_playbook_codes)

    allowlist_cache: Dict[str, Optional[set]] = {}
    playbook_spec_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def _get_allowlist(ws_id: str) -> Optional[set]:
        if ws_id not in allowlist_cache:
            allowlist_cache[ws_id] = _manifest_helper("_load_tool_allowlist")(
                ws_id, binding_store
            )
        return allowlist_cache[ws_id]

    def _get_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
        if playbook_code not in playbook_spec_cache:
            playbook_spec_cache[playbook_code] = _manifest_helper(
                "_load_playbook_spec"
            )(playbook_code)
        return playbook_spec_cache[playbook_code]

    for item in action_items:
        playbook_code = item.get("playbook_code")
        tool_name = item.get("tool_name")
        target_ws = item.get("target_workspace_id") or workspace_id
        allowed_tools = _get_allowlist(target_ws) if binding_store is not None else None

        if isinstance(tool_name, str) and tool_name.strip() and not playbook_code:
            rescued_playbook = _manifest_helper("_resolve_tool_name_playbook_alias")(
                tool_name,
                known_playbook_codes=known_playbook_codes,
                get_playbook_spec=_get_playbook_spec,
            )
            if rescued_playbook:
                item["tool_name_original"] = tool_name
                item["tool_name"] = None
                item["playbook_code"] = rescued_playbook
                item["tool_name_rerouted_to_playbook"] = True
                playbook_code = rescued_playbook
                tool_name = None
            elif allowed_tools is not None:
                canonical_tool, _ = _manifest_helper("_canonicalize_tool_name")(
                    tool_name, allowed_tools
                )
                if canonical_tool and canonical_tool != tool_name:
                    item["tool_name_original"] = tool_name
                    item["tool_name"] = canonical_tool
                    item["tool_name_normalized"] = True
                    tool_name = canonical_tool

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

        if tool_name and binding_store is not None:
            if allowed_tools is not None:
                canonical_tool, candidates = _manifest_helper("_canonicalize_tool_name")(
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
            meeting_session_id=meeting_session_id,
            project_id=project_id,
        )

        warnings: List[Dict[str, Any]] = []
        blocking_findings: List[Dict[str, Any]] = []
        contract_findings = (
            blocking_findings if effective_mode == "block" else warnings
        )

        if playbook_code and manifest_cache and workspace_data_sources is not None:
            required_types = _manifest_helper("_get_consumes_types")(
                playbook_code, manifest_cache
            )
            if required_types:
                resolved_types = _manifest_helper("_get_available_types")(
                    workspace_data_sources
                )
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
