"""Root-or-child convergence for generic tool execution."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.app.dependencies.auth import AuthContext
from backend.app.services.workspace_capability_admission import (
    RootAdmissionRequest,
    WorkspaceCapabilityAdmissionFacade,
)
from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
    verify_child_snapshot,
)
from backend.app.services.workspace_capability_admission.contracts import (
    ExecutionAdmissionSnapshot,
)


_facade = WorkspaceCapabilityAdmissionFacade()
_INTERNAL_KEYS = {
    "execution_admission_snapshot",
    "product_surface_id",
    "active_group_id",
    "observed_topology_revision",
    "operation_type",
    "execution_backend",
    "root_execution_id",
    "trace_id",
    "governance_context",
    "workspace_owner_user_id",
    "group_owner_user_id",
    "allowed_workspace_ids",
    "allowed_group_ids",
}


async def prepare_tool_admission(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    facade: WorkspaceCapabilityAdmissionFacade | None = None,
) -> tuple[dict[str, Any], ExecutionAdmissionSnapshot | None]:
    normalized = dict(arguments)
    existing = normalized.get("execution_admission_snapshot")
    parsed_existing = (
        ExecutionAdmissionSnapshot.model_validate(existing)
        if isinstance(existing, dict)
        else None
    )
    workspace_id = normalized.get("workspace_id")
    if (
        (not isinstance(workspace_id, str) or not workspace_id.strip())
        and parsed_existing is not None
    ):
        workspace_id = parsed_existing.workspace_id
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        return normalized, None
    if parsed_existing is not None:
        parsed = parsed_existing
        snapshot = verify_child_snapshot(
            parsed,
            expected_workspace_id=workspace_id,
            expected_root_execution_id=str(
                normalized.get("root_execution_id")
                or normalized.get("execution_id")
                or parsed.root_execution_id
            ),
        )
    else:
        root_execution_id = str(
            normalized.get("root_execution_id")
            or normalized.get("execution_id")
            or f"tool-{uuid4().hex}"
        )
        active_group_id = normalized.get("active_group_id")
        actor_user_id = str(
            normalized.get("actor_user_id")
            or normalized.get("profile_id")
            or "default-user"
        )
        result = await (facade or _facade).admit_root(
            RootAdmissionRequest(
                workspace_id=workspace_id,
                explicit_active_group_id=(
                    active_group_id
                    if isinstance(active_group_id, str)
                    else None
                ),
                observed_topology_revision=(
                    normalized.get("observed_topology_revision")
                    if isinstance(
                        normalized.get("observed_topology_revision"),
                        int,
                    )
                    else None
                ),
                product_surface_id=(
                    normalized.get("product_surface_id")
                    if isinstance(
                        normalized.get("product_surface_id"),
                        str,
                    )
                    else None
                ),
                selector_kind="tool",
                selector_key=tool_name,
                operation_type=str(
                    normalized.get("operation_type") or "modify"
                ),
                entry="local",
                execution_backend=(
                    "external_provider"
                    if normalized.get("execution_backend") == "remote"
                    else "local"
                ),
                actor_user_id=actor_user_id,
                allowed_workspace_ids=[workspace_id],
                allowed_group_ids=(
                    [active_group_id]
                    if isinstance(active_group_id, str)
                    else []
                ),
                trace_id=str(
                    normalized.get("trace_id") or root_execution_id
                ),
                root_execution_id=root_execution_id,
            )
        )
        snapshot = result.snapshot
    return sanitize_tool_arguments(normalized), snapshot


def sanitize_tool_arguments(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Remove controller-only keys before schema validation."""
    return {
        key: value
        for key, value in arguments.items()
        if key not in _INTERNAL_KEYS
    }
