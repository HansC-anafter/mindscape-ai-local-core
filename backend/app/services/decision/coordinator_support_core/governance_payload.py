"""Governance decision payload helpers for coordinator support."""

from typing import Any, Dict, List, Optional


def build_governance_decision_payload(
    coordinator: Any,
    decision_result: Any,
) -> Optional[Dict[str, Any]]:
    """Build the governance payload shown on DECISION_REQUIRED cards."""
    if (
        decision_result.cost_governance_contribution
        and not decision_result.cost_governance_contribution.approved
    ):
        cost_gov = decision_result.cost_governance_contribution
        workspace_id = getattr(decision_result, "workspace_id", None) or getattr(
            decision_result.intent_contribution, "workspace_id", None
        )
        quota_limit = 0.0
        current_usage = 0.0
        downgrade_suggestion = None

        if getattr(coordinator, "cost_governance", None):
            try:
                quota_settings = coordinator.cost_governance._get_quota_settings(
                    workspace_id or ""
                )
                quota_limit = quota_settings.get("daily_quota", 0.0)
                current_usage = coordinator.cost_governance._get_today_usage(
                    workspace_id or ""
                )
                if cost_gov.reason and "consider" in cost_gov.reason.lower():
                    downgrade_suggestion = cost_gov.reason
            except Exception:
                pass

        return {
            "type": "cost_exceeded",
            "layer": "cost",
            "approved": False,
            "reason": cost_gov.reason,
            "cost_governance": {
                "estimated_cost": cost_gov.estimated_cost or 0.0,
                "quota_limit": quota_limit,
                "current_usage": current_usage,
                "downgrade_suggestion": downgrade_suggestion,
            },
        }

    if (
        decision_result.node_governance_contribution
        and not decision_result.node_governance_contribution.approved
    ):
        node_gov = decision_result.node_governance_contribution
        reason_lower = (node_gov.reason or "").lower()
        if "blacklist" in reason_lower:
            rejection_reason = "blacklist"
        elif "whitelist" in reason_lower:
            rejection_reason = "whitelist"
        elif "risk" in reason_lower or "label" in reason_lower:
            rejection_reason = "risk_label"
        elif "throttle" in reason_lower or "limit" in reason_lower:
            rejection_reason = "throttle"
        else:
            rejection_reason = "unknown"

        return {
            "type": "node_rejected",
            "layer": "node",
            "approved": False,
            "reason": node_gov.reason,
            "node_governance": {
                "rejection_reason": rejection_reason,
                "affected_playbooks": [decision_result.selected_playbook_code]
                if decision_result.selected_playbook_code
                else [],
                "alternatives": [],
            },
        }

    if (
        decision_result.policy_contribution
        and not decision_result.policy_contribution.approved
    ):
        policy = decision_result.policy_contribution
        reason_lower = (policy.reason or "").lower()
        if "role" in reason_lower:
            violation_type = "role"
        elif "domain" in reason_lower or "data" in reason_lower:
            violation_type = "data_domain"
        elif "pii" in reason_lower:
            violation_type = "pii"
        else:
            violation_type = "unknown"

        return {
            "type": "policy_violation",
            "layer": "policy",
            "approved": False,
            "reason": policy.reason,
            "policy_violation": {
                "violation_type": violation_type,
                "policy_id": None,
                "violation_items": [policy.reason] if policy.reason else [],
                "request_permission_url": None,
            },
        }

    if (
        decision_result.playbook_contribution
        and not decision_result.playbook_contribution.accepted
    ):
        preflight = decision_result.playbook_contribution
        missing_credentials: List[str] = []
        environment_issues: List[str] = []
        if preflight.rejection_reason:
            reason_lower = preflight.rejection_reason.lower()
            if (
                "credential" in reason_lower
                or "api key" in reason_lower
                or "key" in reason_lower
            ):
                missing_credentials = [preflight.rejection_reason]
            elif (
                "environment" in reason_lower
                or "sandbox" in reason_lower
                or "repo" in reason_lower
            ):
                environment_issues = [preflight.rejection_reason]

        return {
            "type": "preflight_failed",
            "layer": "preflight",
            "approved": False,
            "reason": preflight.rejection_reason,
            "preflight_failure": {
                "missing_inputs": preflight.missing_inputs or [],
                "missing_credentials": missing_credentials,
                "environment_issues": environment_issues,
                "recommended_alternatives": preflight.recommended_alternatives or [],
            },
        }

    return None
