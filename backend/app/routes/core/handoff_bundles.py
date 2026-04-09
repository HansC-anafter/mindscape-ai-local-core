"""
Handoff Bundle REST API.

Provides endpoints for packaging, verifying, and intaking signed
handoff bundles. These are Layer 0 kernel routes for cross-boundary
task delegation.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.compile_job import CompileJob
from backend.app.models.handoff import Commitment, HandoffIn
from backend.app.models.signed_bundle import SignedHandoffBundle
from backend.app.services.handoff_bundle_service import HandoffBundleService
from backend.app.services.stores.compile_job_store import CompileJobStore

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
    """Verify bundle and extract typed payload.

    Lightweight intake: verifies signature, deserializes payload, returns
    the typed content. Does NOT trigger meeting compile or TaskIR
    persistence. Use POST /compile for the full pipeline.
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


class CompileRequest(BaseModel):
    """Request body for full intake+compile pipeline."""

    bundle: Dict[str, Any] = Field(..., description="SignedHandoffBundle as JSON dict")
    workspace_id: str = Field(..., description="Target workspace for meeting compile")
    project_id: str = Field(..., description="Project scope for meeting session")
    profile_id: str = Field(..., description="User profile triggering the compile")
    thread_id: str = Field(..., description="Conversation thread ID")
    secret_key: Optional[str] = Field(None, description="Override secret")
    model_name: Optional[str] = Field(None, description="LLM model override")
    executor_target_client_id: Optional[str] = Field(
        None,
        description="Optional explicit bridge client target for executor runtime",
    )


@router.get("/compile-jobs/{job_id}")
async def get_compile_job(job_id: str) -> Dict[str, Any]:
    """Get compile job status by ID."""
    store = CompileJobStore()
    job = store.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Compile job not found")
    return job.to_dict()


@router.post("/compile")
async def compile_bundle(request: CompileRequest) -> JSONResponse:
    """Accept a compile job and run the meeting pipeline in the background.

    This is the primary intake entry point for cross-boundary handoffs.
    It verifies the bundle, extracts the HandoffIn, creates a bounded
    meeting session, and schedules the meeting compile in the background.

    ADR-R1: Routes through IngressRouter to share the same routing
    contract as the chat entry point.
    """
    try:
        bundle = SignedHandoffBundle(**request.bundle)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid bundle format: {exc}")

    svc = HandoffBundleService()
    try:
        extracted = svc.extract_payload(bundle, secret_key=request.secret_key)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if extracted["payload_type"] != "handoff_in":
        raise HTTPException(
            status_code=400,
            detail=(
                "Compile requires handoff_in bundle, "
                f"got {extracted['payload_type']}"
            ),
        )
    handoff_in = extracted["payload"]

    # Resolve workspace context
    try:
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        ws_store = PostgresWorkspacesStore()
        workspace = await ws_store.get_workspace(request.workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404,
                detail=f"Workspace {request.workspace_id} not found",
            )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Workspace store not available",
        )

    # --- ADR-R1: Produce RouteDecision via IngressRouter ---
    from backend.app.services.conversation.ingress_router import IngressRouter

    router_instance = IngressRouter()
    route_decision = await router_instance.decide(
        execution_mode="meeting",
        meeting_enabled=True,
        entry_point="compile",
    )

    compile_job_store = CompileJobStore()
    session, session_reused = HandoffBundleService.get_or_create_compile_session(
        handoff_in=handoff_in,
        workspace=workspace,
        profile_id=request.profile_id,
        thread_id=request.thread_id,
        project_id=request.project_id,
    )
    compile_job_metadata = {
        "entry_point": "compile",
        "route_kind": getattr(route_decision, "route_kind", None),
        "model_name": request.model_name,
        "active_session_reused": session_reused,
        "_internal_recovery_context": {
            "handoff_in": handoff_in.model_dump(mode="json"),
            "workspace_id": request.workspace_id,
            "project_id": request.project_id,
            "profile_id": request.profile_id,
            "thread_id": request.thread_id,
            "model_name": request.model_name,
            "source_device_id": bundle.source_device_id,
            "executor_target_client_id": request.executor_target_client_id,
        },
    }
    if request.executor_target_client_id:
        compile_job_metadata["executor_target_client_id"] = (
            request.executor_target_client_id
        )

    compile_job = CompileJob.new(
        workspace_id=request.workspace_id,
        project_id=request.project_id,
        thread_id=request.thread_id,
        profile_id=request.profile_id,
        session_id=session.id,
        handoff_id=(bundle.payload or {}).get("handoff_id"),
        source_device_id=bundle.source_device_id,
        metadata=compile_job_metadata,
    )
    compile_job_store.create(compile_job)
    try:
        from backend.app.services.compile_job_dispatch_manager import (
            get_compile_job_dispatch_manager,
        )

        get_compile_job_dispatch_manager().notify_pending_job()
    except Exception as exc:
        logger.warning(
            "Failed to notify compile job dispatcher for %s: %s",
            compile_job.id,
            exc,
        )

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "job_id": compile_job.id,
            "compile_job_id": compile_job.id,
            "session_id": session.id,
            "workspace_id": request.workspace_id,
            "project_id": request.project_id,
            "thread_id": request.thread_id,
        },
    )
