"""Thin operator boundary for generic deployment-control state."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.backend_runtime_mode import is_execution_plane
from backend.app.dependencies.auth import AuthContext, get_current_operator
from backend.app.services.deployment_control.contracts import (
    DeploymentControlReplaceResult,
    DeploymentControlState,
    ReplaceDeploymentControlCommand,
)
from backend.app.services.deployment_control.errors import (
    DeploymentCatalogConflict,
    DeploymentControlError,
    DeploymentControlStateRevisionConflict,
    DeploymentEnvelopeRevisionConflict,
)
from backend.app.services.deployment_control.facade import DeploymentControlFacade


router = APIRouter(tags=["deployment-control"])


def _facade() -> DeploymentControlFacade:
    return DeploymentControlFacade()


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DeploymentControlStateRevisionConflict):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "expected_revision": exc.expected_revision,
                "server_revision": exc.actual_revision,
            },
        )
    if isinstance(exc, DeploymentEnvelopeRevisionConflict):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "current_envelope_revision": exc.current_revision,
                "requested_envelope_revision": exc.requested_revision,
            },
        )
    if isinstance(exc, DeploymentCatalogConflict):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "expected_catalog_hash": exc.expected_catalog_hash,
                "current_catalog_hash": exc.current_catalog_hash,
            },
        )
    if isinstance(exc, DeploymentControlError):
        return HTTPException(
            status_code=422,
            detail={"error": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=500,
        detail={"error": "deployment_control_failed"},
    )


@router.get(
    "/api/v1/admin/deployment-control",
    response_model=DeploymentControlState,
)
async def get_deployment_control_state(
    _auth: AuthContext = Depends(get_current_operator),
):
    if is_execution_plane():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "deployment_control_requires_control_plane",
                "required_plane": "control",
            },
        )
    try:
        return await asyncio.to_thread(_facade().get_state)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.put(
    "/api/v1/admin/deployment-control",
    response_model=DeploymentControlReplaceResult,
)
async def replace_deployment_control_state(
    command: ReplaceDeploymentControlCommand,
    auth: AuthContext = Depends(get_current_operator),
):
    if is_execution_plane():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "deployment_control_requires_control_plane",
                "required_plane": "control",
            },
        )
    try:
        return await asyncio.to_thread(
            _facade().replace,
            command,
            actor_user_id=auth.user_id,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
