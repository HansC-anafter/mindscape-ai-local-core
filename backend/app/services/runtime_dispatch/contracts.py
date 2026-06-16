"""Contracts shared by runtime dispatch routes and services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.dependencies.auth import AuthContext
from backend.app.services.resource_governance.context import (
    build_resource_governance_context,
    require_workspace_resource_access,
)

from .feature_gate import get_runtime_dispatch_feature_gate

DEFAULT_SOURCE_SURFACE = "settings_host_resources"
DEFAULT_REASON = "runtime_dispatch_request"


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


@dataclass(frozen=True)
class DispatchRequestContext:
    actor_id: str
    workspace_id: str
    trace_id: str | None
    source_surface: str
    reason: str
    auth_scope: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "workspace_id": self.workspace_id,
            "trace_id": self.trace_id,
            "source_surface": self.source_surface,
            "reason": self.reason,
            "auth_scope": self.auth_scope,
        }


def build_dispatch_request_context(
    auth_context: AuthContext,
    *,
    workspace_id: str | None,
    trace_id: str | None = None,
    source_surface: str | None = None,
    reason: str | None = None,
) -> DispatchRequestContext:
    normalized_workspace_id = require_workspace_resource_access(
        auth_context,
        workspace_id,
    )
    actor_id = _clean_string(getattr(auth_context, "user_id", None)) or "unknown_actor"
    return DispatchRequestContext(
        actor_id=actor_id,
        workspace_id=normalized_workspace_id,
        trace_id=_clean_string(trace_id),
        source_surface=_clean_string(source_surface) or DEFAULT_SOURCE_SURFACE,
        reason=_clean_string(reason) or DEFAULT_REASON,
        auth_scope=build_resource_governance_context(
            auth_context,
            workspace_id=normalized_workspace_id,
            requested_mode="workspace",
        ),
    )


def disabled_dispatch_result(
    operation: str,
    *,
    context: DispatchRequestContext | None = None,
) -> dict[str, Any]:
    return {
        "accepted": False,
        "state": "rejected",
        "operation": operation,
        "reason": "runtime_dispatch_disabled",
        "feature_gate": get_runtime_dispatch_feature_gate(),
        "context": context.to_dict() if context else None,
        "mutation_performed": False,
        "db_mutation_performed": False,
        "redis_mutation_performed": False,
        "repair_required": False,
    }


def not_implemented_dispatch_result(
    operation: str,
    *,
    context: DispatchRequestContext,
) -> dict[str, Any]:
    return {
        "accepted": False,
        "state": "rejected",
        "operation": operation,
        "reason": "runtime_dispatch_not_implemented",
        "feature_gate": get_runtime_dispatch_feature_gate(),
        "context": context.to_dict(),
        "mutation_performed": False,
        "db_mutation_performed": False,
        "redis_mutation_performed": False,
        "repair_required": False,
    }
