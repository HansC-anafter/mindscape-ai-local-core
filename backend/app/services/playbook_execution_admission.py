"""Thin playbook-root adapter to the workspace admission facade."""

from __future__ import annotations

from backend.app.dependencies.auth import AuthContext
from backend.app.services.workspace_capability_admission import (
    RootAdmissionRequest,
    RootAdmissionResult,
    WorkspaceCapabilityAdmissionFacade,
)


_facade = WorkspaceCapabilityAdmissionFacade()


async def admit_playbook_root(
    *,
    workspace_id: str,
    product_surface_id: str | None,
    active_group_id: str | None,
    observed_topology_revision: int | None,
    playbook_code: str,
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
            selector_kind="playbook",
            selector_key=playbook_code,
            operation_type="generate",
            entry="remote" if remote_ingress_verified else "local",
            remote_ingress_verified=remote_ingress_verified,
            execution_backend=(
                "external_provider"
                if execution_backend == "remote"
                else "local"
            ),
            actor_user_id=auth.user_id,
            allowed_workspace_ids=auth.workspace_ids,
            allowed_group_ids=auth.group_ids,
            trace_id=trace_id,
            root_execution_id=root_execution_id,
        )
    )

