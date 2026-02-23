"""
Handoff Bundle REST API.

Provides endpoints for packaging, verifying, and intaking signed
handoff bundles. These are Layer 0 kernel routes for cross-boundary
task delegation.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.handoff import Commitment, HandoffIn
from backend.app.models.signed_bundle import SignedHandoffBundle
from backend.app.services.handoff_bundle_service import HandoffBundleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/handoff-bundles", tags=["handoff-bundles"])


# -- Request / Response schemas ---------------------------------------------


class PackageRequest(BaseModel):
    """Request body for packaging a HandoffIn or Commitment."""

    payload_type: str = Field(..., description="handoff_in or commitment")
    payload: Dict[str, Any] = Field(
        ..., description="HandoffIn or Commitment as JSON dict"
    )
    source_device_id: str = Field(..., description="Originating device ID")
    target_device_id: Optional[str] = Field(
        None, description="Intended recipient device ID"
    )
    secret_key: Optional[str] = Field(
        None, description="Override signing secret (defaults to env var)"
    )


class VerifyRequest(BaseModel):
    """Request body for verifying a bundle."""

    bundle: Dict[str, Any] = Field(..., description="SignedHandoffBundle as JSON dict")
    secret_key: Optional[str] = Field(None, description="Override secret")


class IntakeRequest(BaseModel):
    """Request body for intaking (verify + extract) a bundle."""

    bundle: Dict[str, Any] = Field(..., description="SignedHandoffBundle as JSON dict")
    secret_key: Optional[str] = Field(None, description="Override secret")
    workspace_id: Optional[str] = Field(None, description="Target workspace for intake")


class VerifyResponse(BaseModel):
    """Response for bundle verification."""

    valid: bool
    payload_type: Optional[str] = None
    source_device_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# -- Endpoints ---------------------------------------------------------------


@router.post("/package")
async def package_bundle(request: PackageRequest) -> Dict[str, Any]:
    """Package a HandoffIn or Commitment into a signed bundle.

    Returns the signed bundle as JSON, ready for transport via any channel.
    """
    svc = HandoffBundleService()

    try:
        if request.payload_type == "handoff_in":
            handoff_in = HandoffIn(**request.payload)
            bundle = svc.package_handoff(
                handoff_in=handoff_in,
                source_device_id=request.source_device_id,
                secret_key=request.secret_key,
                target_device_id=request.target_device_id,
            )
        elif request.payload_type == "commitment":
            commitment = Commitment(**request.payload)
            bundle = svc.package_commitment(
                commitment=commitment,
                source_device_id=request.source_device_id,
                secret_key=request.secret_key,
                target_device_id=request.target_device_id,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported payload_type: {request.payload_type}",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return bundle.model_dump(mode="json")


@router.post("/verify", response_model=VerifyResponse)
async def verify_bundle(request: VerifyRequest) -> VerifyResponse:
    """Verify a bundle's signature and integrity without intaking it."""
    try:
        bundle = SignedHandoffBundle(**request.bundle)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid bundle format: {exc}")

    svc = HandoffBundleService()
    try:
        valid = svc.verify_bundle(bundle, secret_key=request.secret_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return VerifyResponse(
        valid=valid,
        payload_type=bundle.payload_type if valid else None,
        source_device_id=bundle.source_device_id if valid else None,
    )


@router.post("/intake")
async def intake_bundle(request: IntakeRequest) -> Dict[str, Any]:
    """Verify bundle and extract typed payload for processing.

    For handoff_in: returns the deserialized HandoffIn ready for
    meeting engine compilation.
    For commitment: returns the deserialized Commitment.
    """
    try:
        bundle = SignedHandoffBundle(**request.bundle)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid bundle format: {exc}")

    svc = HandoffBundleService()
    try:
        result = svc.extract_payload(bundle, secret_key=request.secret_key)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    payload = result["payload"]
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")

    return {
        "payload_type": result["payload_type"],
        "payload": payload,
        "source_device_id": bundle.source_device_id,
        "verified": True,
    }
