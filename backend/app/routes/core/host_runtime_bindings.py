"""Thin HTTP boundary for host binding and workspace grant authority."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.backend_runtime_mode import is_execution_plane
from backend.app.dependencies.auth import (
    AuthContext,
    get_current_operator,
    get_current_user,
)
from backend.app.services.host_runtime_bindings.contracts import (
    AttestBindingCommand,
    DeclareBindingCommand,
    EffectiveHostAdmissionProjection,
    FinalizeBindingRetirementCommand,
    GrantWorkspaceCommand,
    HostOperation,
    HostRuntimeCommandReceipt,
    HostRuntimeExecutionPermit,
    HostRuntimeExecutionPermitRequest,
    MaterializationReceiptCommand,
    RequestBindingRetirementCommand,
)
from backend.app.services.host_runtime_bindings.facade import (
    HostRuntimeBindingFacade,
)
from backend.app.services.device_node_host_runtime_client import (
    DeviceNodeHostRuntimeClient,
)
from backend.app.services.host_runtime_execution_permit_coordinator import (
    HostRuntimeExecutionPermitCoordinator,
)


router = APIRouter(tags=["host-runtime-bindings"])
facade = HostRuntimeBindingFacade()
device_node_client = DeviceNodeHostRuntimeClient()
execution_permit_coordinator = HostRuntimeExecutionPermitCoordinator(
    facade=facade,
    device_node_client=device_node_client,
)


def _require_control_plane() -> None:
    if is_execution_plane():
        raise HTTPException(
            status_code=409,
            detail={"error": "host_runtime_mutation_requires_control_plane"},
        )


def _translate(exc: Exception) -> HTTPException:
    code = str(exc)
    status = 409 if "conflict" in code or "mismatch" in code else 422
    return HTTPException(status_code=status, detail={"error": code[:160]})


@router.post(
    "/api/v1/admin/host-runtime-bindings",
    response_model=HostRuntimeCommandReceipt,
)
async def declare_host_runtime_binding(
    command: DeclareBindingCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        binding_id = await asyncio.to_thread(
            facade.declare_binding,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="declare",
            binding_id=binding_id,
            generation=command.expected_generation + 1,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/admin/host-runtime-bindings/materializations",
    response_model=HostRuntimeCommandReceipt,
)
async def record_host_runtime_materialization(
    command: MaterializationReceiptCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        await asyncio.to_thread(
            facade.record_materialization,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="materialize",
            binding_id=command.binding_id,
            generation=command.generation,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/admin/host-runtime-bindings/attestations",
    response_model=HostRuntimeCommandReceipt,
)
async def record_host_runtime_attestation(
    command: AttestBindingCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        revision = await asyncio.to_thread(
            facade.record_attestation,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="attest",
            binding_id=command.binding_id,
            generation=command.generation,
            revision=revision,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/admin/host-runtime-bindings/{binding_id}/reconcile",
    response_model=HostRuntimeCommandReceipt,
)
async def reconcile_host_runtime_binding(
    binding_id: str,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        binding = await asyncio.to_thread(facade.get_binding, binding_id)
        command = await device_node_client.attest_binding(binding)
        revision = await asyncio.to_thread(
            facade.record_attestation,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="attest",
            binding_id=binding_id,
            generation=command.generation,
            revision=revision,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/workspaces/{workspace_id}/host-runtime-grants",
    response_model=HostRuntimeCommandReceipt,
)
async def grant_workspace_host_runtime(
    workspace_id: str,
    command: GrantWorkspaceCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    if workspace_id != command.workspace_id:
        raise HTTPException(
            status_code=422,
            detail={"error": "workspace_host_grant_workspace_mismatch"},
        )
    try:
        grant_id = await asyncio.to_thread(
            facade.grant_workspace,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="grant",
            binding_id=command.binding_id,
            grant_id=grant_id,
            generation=command.binding_generation,
            revision=command.policy_revision,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.delete(
    "/api/v1/admin/host-runtime-grants/{grant_id}",
    response_model=HostRuntimeCommandReceipt,
)
async def revoke_workspace_host_runtime(
    grant_id: str,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        await asyncio.to_thread(
            facade.revoke_workspace_grant,
            grant_id,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(command="revoke", grant_id=grant_id)
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/admin/host-runtime-bindings/retirements",
    response_model=HostRuntimeCommandReceipt,
)
async def request_host_runtime_binding_retirement(
    command: RequestBindingRetirementCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        await asyncio.to_thread(
            facade.request_binding_retirement,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="retire",
            binding_id=command.binding_id,
            generation=command.generation,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/admin/host-runtime-bindings/retirement-finalizations",
    response_model=HostRuntimeCommandReceipt,
)
async def finalize_host_runtime_binding_retirement(
    command: FinalizeBindingRetirementCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane()
    try:
        await asyncio.to_thread(
            facade.finalize_binding_retirement,
            command,
            actor_id=auth.user_id,
        )
        return HostRuntimeCommandReceipt(
            command="retire",
            binding_id=command.binding_id,
            generation=command.generation,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/api/v1/workspaces/{workspace_id}/host-runtime-bindings/"
    "{capability_code}/{requirement_code}/{operation}",
    response_model=EffectiveHostAdmissionProjection,
)
async def get_effective_host_runtime_admission(
    workspace_id: str,
    capability_code: str,
    requirement_code: str,
    operation: HostOperation,
    auth: AuthContext = Depends(get_current_user),
):
    if workspace_id not in auth.workspace_ids:
        raise HTTPException(status_code=403, detail={"error": "workspace_forbidden"})
    try:
        return await asyncio.to_thread(
            facade.resolve_effective_admission,
            workspace_id=workspace_id,
            capability_code=capability_code,
            requirement_code=requirement_code,
            operation=operation,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/api/v1/workspaces/{workspace_id}/host-runtime-execution-permits/"
    "{capability_code}/{requirement_code}/{operation}",
    response_model=HostRuntimeExecutionPermit,
)
async def issue_host_runtime_execution_permit(
    workspace_id: str,
    capability_code: str,
    requirement_code: str,
    operation: HostOperation,
    command: HostRuntimeExecutionPermitRequest,
    auth: AuthContext = Depends(get_current_user),
):
    _require_control_plane()
    if workspace_id not in auth.workspace_ids:
        raise HTTPException(status_code=403, detail={"error": "workspace_forbidden"})
    try:
        return await execution_permit_coordinator.issue(
            workspace_id=workspace_id,
            capability_code=capability_code,
            requirement_code=requirement_code,
            operation=operation,
            operation_args=command.operation_args,
            ttl_seconds=command.ttl_seconds,
            actor_id=auth.user_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc
