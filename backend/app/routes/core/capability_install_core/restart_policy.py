"""Restart decision policy for capability installs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


INSTALL_RESTART_SEMANTICS_VERSION = "install_restart_decision_v2"


@dataclass(frozen=True)
class InstallRestartDecision:
    execution_activation_required: bool = True
    execution_activation_state: str = "pending_activation"
    backend_process_restart_required: bool = False
    runner_restart_required: bool = False
    restart_webhook_required: bool = False
    legacy_restart_required: bool = False
    reasons: List[str] = field(default_factory=list)
    semantic_version: str = INSTALL_RESTART_SEMANTICS_VERSION

    def to_payload(self) -> Dict[str, Any]:
        return {
            "execution_activation_required": self.execution_activation_required,
            "execution_activation_state": self.execution_activation_state,
            "backend_process_restart_required": self.backend_process_restart_required,
            "runner_restart_required": self.runner_restart_required,
            "restart_webhook_required": self.restart_webhook_required,
            "legacy_restart_required": self.legacy_restart_required,
            "reasons": list(self.reasons),
            "semantic_version": self.semantic_version,
        }


def build_install_restart_decision(
    *,
    contract_lane_changed: bool = False,
    execution_activation_state: Optional[str] = None,
    activation_state: Optional[str] = None,
    manifest_hash_matches: Optional[bool] = None,
    backend_restart_triggered: bool = False,
    hot_reload_performed: bool = False,
) -> InstallRestartDecision:
    state = execution_activation_state or "pending_activation"
    reasons = [
        "pack_install_requires_execution_activation",
        "runner_restart_not_required_for_pack_install",
    ]

    backend_restart_required = bool(contract_lane_changed)
    if contract_lane_changed:
        reasons.append("contract_lane_changed")

    if backend_restart_triggered:
        backend_restart_required = False
        reasons.append("backend_reload_triggered")
    elif hot_reload_performed:
        reasons.append("in_process_hot_reload_completed")

    if state == "activated":
        reasons.append("execution_activation_activated")
    elif state in {"pending_activation", "pending_execution_activation"}:
        reasons.append("execution_activation_pending")

    if activation_state == "active":
        reasons.append("activation_state_active")
    if manifest_hash_matches is True:
        reasons.append("manifest_hash_matched")
    elif manifest_hash_matches is False:
        reasons.append("manifest_hash_mismatched")

    return InstallRestartDecision(
        execution_activation_required=True,
        execution_activation_state=state,
        backend_process_restart_required=backend_restart_required,
        runner_restart_required=False,
        restart_webhook_required=backend_restart_required,
        legacy_restart_required=backend_restart_required,
        reasons=_dedupe_reasons(reasons),
    )


def apply_restart_decision_to_payload(
    payload: Dict[str, Any],
    decision: InstallRestartDecision | Dict[str, Any],
) -> Dict[str, Any]:
    decision_payload = (
        decision.to_payload()
        if isinstance(decision, InstallRestartDecision)
        else _normalize_decision_payload(decision)
    )
    next_payload = dict(payload)
    next_payload["restart_decision"] = decision_payload
    next_payload["restart_required"] = bool(
        decision_payload["backend_process_restart_required"]
    )
    next_payload["backend_process_restart_required"] = bool(
        decision_payload["backend_process_restart_required"]
    )
    next_payload["runner_restart_required"] = bool(
        decision_payload["runner_restart_required"]
    )
    next_payload["execution_activation_required"] = bool(
        decision_payload["execution_activation_required"]
    )
    next_payload["execution_activation_state"] = str(
        decision_payload["execution_activation_state"]
    )
    next_payload["restart_semantics_version"] = str(
        decision_payload["semantic_version"]
    )
    return next_payload


def refresh_restart_decision_after_execution(
    *,
    payload: Dict[str, Any],
    execution_activation: Optional[Dict[str, Any]],
    activation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    existing_decision = _normalize_decision_payload(payload.get("restart_decision"))
    reasons = set(existing_decision.get("reasons") or [])
    execution_state = (
        (execution_activation or {}).get("state")
        or existing_decision.get("execution_activation_state")
        or "pending_activation"
    )
    activation_state = (activation or {}).get("activation_state")
    manifest_hash_matches = _manifest_hash_matches(payload=payload, activation=activation)
    decision = build_install_restart_decision(
        contract_lane_changed="contract_lane_changed" in reasons,
        execution_activation_state=str(execution_state),
        activation_state=activation_state,
        manifest_hash_matches=manifest_hash_matches,
        backend_restart_triggered=bool(payload.get("restart_triggered")),
    )
    return apply_restart_decision_to_payload(payload, decision)


def _normalize_decision_payload(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    backend_restart_required = bool(value.get("backend_process_restart_required"))
    runner_restart_required = bool(value.get("runner_restart_required", False))
    execution_activation_required = bool(
        value.get("execution_activation_required", True)
    )
    execution_activation_state = str(
        value.get("execution_activation_state") or "pending_activation"
    )
    return {
        "execution_activation_required": execution_activation_required,
        "execution_activation_state": execution_activation_state,
        "backend_process_restart_required": backend_restart_required,
        "runner_restart_required": runner_restart_required,
        "restart_webhook_required": bool(
            value.get("restart_webhook_required", backend_restart_required)
        ),
        "legacy_restart_required": bool(
            value.get("legacy_restart_required", backend_restart_required)
        ),
        "reasons": list(value.get("reasons") or []),
        "semantic_version": str(
            value.get("semantic_version") or INSTALL_RESTART_SEMANTICS_VERSION
        ),
    }


def _manifest_hash_matches(
    *,
    payload: Dict[str, Any],
    activation: Optional[Dict[str, Any]],
) -> Optional[bool]:
    if not activation:
        return None
    pending_hash = (payload.get("activation") or {}).get("manifest_hash")
    current_hash = activation.get("manifest_hash")
    if not pending_hash or not current_hash:
        return None
    return bool(pending_hash == current_hash)


def _dedupe_reasons(reasons: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for reason in reasons:
        if reason and reason not in seen:
            seen.add(reason)
            deduped.append(reason)
    return deduped
