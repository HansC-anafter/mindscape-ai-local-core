"""Approval audit event helpers for host runtime sessions."""

from __future__ import annotations

from typing import Any, Literal

from .models import new_id, utc_now


ApprovalDecision = Literal["approved", "denied"]


def build_approval_audit_payload(
    *,
    approval_id: str,
    decision: ApprovalDecision,
    actor_id: str | None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "audit_id": new_id("approval_audit"),
        "approval_id": approval_id,
        "decision": decision,
        "actor_id": actor_id,
        "reason": reason,
        "metadata": metadata or {},
        "recorded_at": utc_now().isoformat(),
    }
