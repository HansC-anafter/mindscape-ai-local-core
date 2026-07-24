"""Thin Meeting root adapter to workspace capability admission."""

from __future__ import annotations

from backend.app.dependencies.auth import AuthContext
from backend.app.services.workspace_capability_admission import (
    RootAdmissionRequest,
    RootAdmissionResult,
    WorkspaceCapabilityAdmissionFacade,
)


_facade = WorkspaceCapabilityAdmissionFacade()


def meeting_admission_context(session) -> dict:
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    snapshot = metadata.get("execution_admission_snapshot")
    root_execution_id = metadata.get("root_execution_id")
    if not isinstance(snapshot, dict) or not isinstance(root_execution_id, str):
        return {}
    return {
        "execution_admission_snapshot": snapshot,
        "root_execution_id": root_execution_id,
    }


async def admit_meeting_root(
    *,
    workspace_id: str,
    active_group_id: str | None,
    observed_topology_revision: int | None,
    product_surface_id: str | None,
    selector_kind: str,
    selector_key: str,
    operation_type: str,
    execution_backend: str,
    remote_ingress_verified: bool,
    auth: AuthContext,
    trace_id: str,
    root_execution_id: str,
    facade: WorkspaceCapabilityAdmissionFacade | None = None,
) -> RootAdmissionResult:
    return await (facade or _facade).admit_root(
        RootAdmissionRequest(
            workspace_id=workspace_id,
            explicit_active_group_id=active_group_id,
            observed_topology_revision=observed_topology_revision,
            product_surface_id=product_surface_id,
            selector_kind=selector_kind,
            selector_key=selector_key,
            operation_type=operation_type,
            entry="remote" if remote_ingress_verified else "local",
            remote_ingress_verified=remote_ingress_verified,
            execution_backend=execution_backend,
            actor_user_id=auth.user_id,
            allowed_workspace_ids=auth.workspace_ids,
            allowed_group_ids=auth.group_ids,
            trace_id=trace_id,
            root_execution_id=root_execution_id,
        )
    )
