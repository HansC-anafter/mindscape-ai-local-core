"""Admin endpoint for explicit capability runtime activation."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from backend.app.services.capability_runtime_activation import (
    activate_installed_capability_routes,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class CapabilityRuntimeActivationRequest(BaseModel):
    capability_code: str = Field(..., min_length=1)
    install_id: Optional[str] = None
    manifest_hash: Optional[str] = None
    artifact_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason: str = "install_completed"


@router.post("/capability-runtime/activate")
async def activate_capability_runtime(
    request: Request,
    payload: CapabilityRuntimeActivationRequest,
):
    try:
        result = await asyncio.to_thread(
            activate_installed_capability_routes,
            app=request.app,
            capability_code=payload.capability_code,
            reason=payload.reason,
            expected_manifest_hash=payload.manifest_hash,
            installed_artifact_sha256=payload.artifact_sha256,
        )
        result["install_id"] = payload.install_id
        result["requested_manifest_hash"] = payload.manifest_hash
        result["requested_artifact_sha256"] = payload.artifact_sha256
        return result
    except Exception as exc:
        logger.warning(
            "Capability runtime activation pending for %s: %s",
            payload.capability_code,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=202,
            content={
                "state": "pending_activation",
                "capability_code": payload.capability_code,
                "install_id": payload.install_id,
                "error": str(exc),
            },
        )
