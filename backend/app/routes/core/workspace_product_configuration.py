"""Thin HTTP boundary for PCS catalog and workspace product configuration."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.core.backend_runtime_mode import is_execution_plane
from backend.app.dependencies.auth import (
    AuthContext,
    get_current_operator,
    get_current_user,
)
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupNotFoundError,
)
from backend.app.services.workspace_product_configuration.contracts import (
    CatalogImportResult,
    ReplaceScopeCommand,
    WorkspaceCapabilitySetSnapshot,
)
from backend.app.services.deployment_control.facade import DeploymentControlFacade
from backend.app.services.workspace_product_configuration.errors import (
    ActiveCatalogMissingError,
    CatalogRevisionConflictError,
    ScopeAccessError,
    ScopeRevisionConflictError,
    TopologyRevisionConflictError,
    WorkspaceProductConfigurationError,
)
from backend.app.services.workspace_product_configuration.facade import (
    WorkspaceProductConfigurationFacade,
)


router = APIRouter(tags=["workspace-product-configuration"])
facade = WorkspaceProductConfigurationFacade()
deployment_facade = DeploymentControlFacade()


def _auth(auth: AuthContext) -> dict[str, Any]:
    return {
        "actor_user_id": auth.user_id,
        "allowed_workspace_ids": auth.workspace_ids,
        "allowed_group_ids": auth.group_ids,
    }


def _require_control_plane_mutation() -> None:
    if is_execution_plane():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "workspace_product_mutation_requires_control_plane",
                "required_plane": "control",
            },
        )


def _with_deployment_control(
    snapshot: WorkspaceCapabilitySetSnapshot,
) -> WorkspaceCapabilitySetSnapshot:
    ceiling = deployment_facade.resolve_effective_ceiling(snapshot)
    return WorkspaceCapabilitySetSnapshot.model_validate(
        {
            **snapshot.model_dump(mode="json"),
            "deployment_control": {
                "mode": ceiling.mode,
                "provider_code": ceiling.provider_code,
                "state_revision": ceiling.state_revision,
                "envelope_revision": ceiling.envelope_revision,
                "envelope_hash": ceiling.envelope_hash,
                "permitted_surface_ids": sorted(
                    {
                        surface
                        for assignment in ceiling.assignments
                        for surface in assignment.allowed_surface_ids
                    }
                ),
            },
        }
    )


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CatalogRevisionConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "expected_catalog_hash": exc.expected_catalog_hash,
                "current_catalog_hash": exc.current_catalog_hash,
            },
        )
    if isinstance(exc, ScopeRevisionConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "expected_revision": exc.expected_revision,
                "server_revision": exc.actual_revision,
                "current_catalog_hash": exc.current_catalog_hash,
            },
        )
    if isinstance(exc, TopologyRevisionConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "expected_revision": exc.expected_revision,
                "server_revision": exc.actual_revision,
            },
        )
    if isinstance(exc, (ScopeAccessError, WorkspaceGroupAccessError)):
        return HTTPException(
            status_code=403,
            detail={"error": getattr(exc, "code", "workspace_group_forbidden")},
        )
    if isinstance(exc, WorkspaceGroupNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ActiveCatalogMissingError):
        return HTTPException(status_code=409, detail={"error": exc.code})
    if isinstance(exc, WorkspaceProductConfigurationError):
        return HTTPException(
            status_code=422,
            detail={"error": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=500,
        detail={"error": "workspace_product_configuration_failed"},
    )


@router.post(
    "/api/v1/admin/product-capability-catalog/import",
    response_model=CatalogImportResult,
)
async def import_product_capability_catalog(
    artifact: dict[str, Any],
    auth: AuthContext = Depends(get_current_operator),
):
    _require_control_plane_mutation()
    try:
        return await asyncio.to_thread(
            facade.import_catalog,
            artifact,
            actor_user_id=auth.user_id,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get(
    "/api/v1/workspaces/{workspace_id}/product-configuration/effective",
    response_model=WorkspaceCapabilitySetSnapshot,
)
async def get_effective_workspace_product_configuration(
    workspace_id: str,
    active_group_id: str | None = Query(default=None),
    observed_topology_revision: int | None = Query(default=None, ge=1),
    auth: AuthContext = Depends(get_current_user),
):
    try:
        snapshot = await asyncio.to_thread(
            facade.resolve_snapshot,
            workspace_id=workspace_id,
            explicit_active_group_id=active_group_id,
            observed_topology_revision=observed_topology_revision,
            **_auth(auth),
        )
        return await asyncio.to_thread(_with_deployment_control, snapshot)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.put(
    "/api/v1/workspaces/{workspace_id}/product-configuration",
    response_model=WorkspaceCapabilitySetSnapshot,
)
async def replace_workspace_product_configuration(
    workspace_id: str,
    command: ReplaceScopeCommand,
    active_group_id: str | None = Query(default=None),
    observed_topology_revision: int | None = Query(default=None, ge=1),
    auth: AuthContext = Depends(get_current_user),
):
    _require_control_plane_mutation()
    try:
        snapshot = await asyncio.to_thread(
            facade.replace_scope,
            scope_kind="workspace",
            scope_id=workspace_id,
            workspace_id=workspace_id,
            explicit_active_group_id=active_group_id,
            observed_topology_revision=observed_topology_revision,
            command=command,
            **_auth(auth),
        )
        return await asyncio.to_thread(_with_deployment_control, snapshot)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.put(
    "/api/v1/workspace-groups/{group_id}/product-configuration",
    response_model=WorkspaceCapabilitySetSnapshot,
)
async def replace_workspace_group_product_configuration(
    group_id: str,
    command: ReplaceScopeCommand,
    workspace_id: str = Query(min_length=1),
    observed_topology_revision: int | None = Query(default=None, ge=1),
    auth: AuthContext = Depends(get_current_user),
):
    _require_control_plane_mutation()
    try:
        snapshot = await asyncio.to_thread(
            facade.replace_scope,
            scope_kind="workspace_group",
            scope_id=group_id,
            workspace_id=workspace_id,
            explicit_active_group_id=group_id,
            observed_topology_revision=observed_topology_revision,
            command=command,
            **_auth(auth),
        )
        return await asyncio.to_thread(_with_deployment_control, snapshot)
    except Exception as exc:
        raise _translate_error(exc) from exc
