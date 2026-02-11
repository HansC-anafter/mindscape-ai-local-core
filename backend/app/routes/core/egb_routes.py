"""
EGB API Routes

Provides EGB-related API endpoints:
- GET /api/v1/egb/run/{run_id}/drift
- GET /api/v1/egb/intent/{intent_id}/profile
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.egb.services.egb_orchestrator import EGBOrchestrator
from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
from backend.app.egb.schemas.drift_report import RunDriftReport
from backend.app.egb.schemas.evidence_profile import IntentEvidenceProfile
from backend.app.core.database import get_db  # Assume this dependency exists

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/egb", tags=["egb"])


def get_orchestrator(db: AsyncSession = Depends(get_db)) -> EGBOrchestrator:
    """Get EGB Orchestrator instance"""
    from backend.app.egb.integrations.langfuse_adapter import LangfuseAdapter

    store = EvidenceProfileStore(db)
    langfuse_adapter = LangfuseAdapter()
    langfuse_adapter.initialize()  # Initialize LangfuseAdapter

    return EGBOrchestrator(
        store=store,
        langfuse_adapter=langfuse_adapter,  # Inject LangfuseAdapter
    )


@router.get("/run/{run_id}/drift", response_model=RunDriftReport)
async def get_run_drift(
    run_id: str,
    baseline_run_id: Optional[str] = Query(None, description="Baseline Run ID (optional, uses BaselinePicker if not provided)"),
    orchestrator: EGBOrchestrator = Depends(get_orchestrator),
) -> RunDriftReport:
    """
    Get execution drift report

    Planned interface: Complete drift report flow
    1. Get correlation_ids from run_index
    2. Adapter pulls raw trace
    3. Normalizer → graph
    4. Reducer → evidence (cacheable)
    5. Baseline picker (if baseline_run_id not specified)
    6. Reducer baseline evidence (cacheable)
    7. Drift scorer
    8. Store + return

    Args:
        run_id: Execution ID
        baseline_run_id: Baseline execution ID (optional)

    Returns:
        RunDriftReport: Drift report
    """
    try:
        drift_report = await orchestrator.get_drift_report(
            run_id=run_id,
            baseline_run_id=baseline_run_id,
        )

        if not drift_report:
            raise HTTPException(
                status_code=404,
                detail=f"Drift report not found for run {run_id}"
            )

        return drift_report

    except Exception as e:
        logger.error(f"Failed to get drift report for run {run_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get drift report: {str(e)}"
        )


@router.get("/intent/{intent_id}/profile", response_model=IntentEvidenceProfile)
async def get_intent_profile(
    intent_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
    policy_version: Optional[str] = Query(None, description="Policy version (optional)"),
    orchestrator: EGBOrchestrator = Depends(get_orchestrator),
) -> IntentEvidenceProfile:
    """
    Get intent evidence profile

    Includes:
    - Stability score (EMA)
    - Cost statistics
    - Execution statistics

    Args:
        intent_id: Intent ID
        workspace_id: Workspace ID
        policy_version: Policy version (optional)

    Returns:
        IntentEvidenceProfile: Intent evidence profile
    """
    try:
        profile = await orchestrator.get_intent_profile(
            intent_id=intent_id,
            workspace_id=workspace_id,
        )

        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"Profile not found for intent {intent_id}"
            )

        return profile

    except Exception as e:
        logger.error(f"Failed to get profile for intent {intent_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get profile: {str(e)}"
        )


@router.post("/run/{run_id}/register")
async def register_run(
    run_id: str,
    correlation_ids: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """
    Register Run (create index)

    Planned interface: register_run only creates index
    """
    from backend.app.egb.schemas.correlation_ids import CorrelationIds
    from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore

    try:
        # Build CorrelationIds from request body
        correlation_ids_obj = CorrelationIds.from_dict(correlation_ids)
        # Ensure run_id is consistent
        correlation_ids_obj.run_id = run_id

        # Save to store
        store = EvidenceProfileStore(db)
        run_index = await store.save_run_index(
            correlation_ids=correlation_ids_obj,
            status="pending",
        )

        return {
            "run_id": run_index.run_id,
            "intent_id": run_index.intent_id,
            "workspace_id": run_index.workspace_id,
            "status": run_index.status,
        }

    except Exception as e:
        logger.error(f"Failed to register run {run_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register run: {str(e)}"
        )


@router.get("/run/{run_id}/status")
async def get_run_status(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get Run status

    Returns basic information from run_index
    """
    from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore

    try:
        store = EvidenceProfileStore(db)
        run_index = await store.get_run_index(run_id)

        if not run_index:
            raise HTTPException(
                status_code=404,
                detail=f"Run {run_id} not found"
            )

        return {
            "run_id": run_index.run_id,
            "intent_id": run_index.intent_id,
            "workspace_id": run_index.workspace_id,
            "status": run_index.status,
            "outcome": run_index.outcome,
            "is_success": run_index.is_success,
            "gate_passed": run_index.gate_passed,
            "error_count": run_index.error_count,
            "strictness_level": run_index.strictness_level,
            "mind_lens_level": run_index.mind_lens_level,
            "policy_version": run_index.policy_version,
            "created_at": run_index.created_at.isoformat(),
            "updated_at": run_index.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get run status for {run_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get run status: {str(e)}"
        )


@router.get("/external-job/{external_job_id}/run")
async def get_run_by_external_job(
    external_job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get run_id by external_job_id

    P0-7 acceptance criteria: Can reverse lookup run_id from external_job_id
    """
    from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore

    store = EvidenceProfileStore(db)
    mapping = await store.get_external_job_mapping(external_job_id)

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"External job {external_job_id} not found"
        )

    return {
        "external_job_id": mapping.external_job_id,
        "run_id": mapping.run_id,
        "span_id": mapping.span_id,
        "tool_name": mapping.tool_name,
        "status": mapping.status,
    }


@router.post("/external-job/callback")
async def handle_external_job_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle external job callback

    P0-7 hard rule: When external callback arrives, automatically update corresponding span status
    """
    from backend.app.egb.integrations.external_boundary import get_external_boundary
    from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore

    # Extract headers and body
    headers = dict(request.headers)
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}

    boundary = get_external_boundary()
    correlation_ids = boundary.extract_inbound_correlation(headers=headers, metadata=body)
    span_id = boundary.extract_span_id(headers=headers, metadata=body)

    if not correlation_ids:
        raise HTTPException(
            status_code=400,
            detail="Missing correlation headers/metadata in callback"
        )

    # Extract external_job_id from body or headers
    external_job_id = body.get("job_id") or body.get("external_job_id") or headers.get("X-External-Job-Id")
    if not external_job_id:
        raise HTTPException(
            status_code=400,
            detail="Missing external_job_id in callback"
        )

    # Update ExternalJobMapping status
    store = EvidenceProfileStore(db)
    mapping = await store.get_external_job_mapping(external_job_id)

    if not mapping:
        # If no mapping exists, create one
        tool_name = body.get("tool_name") or headers.get("X-Tool-Name") or "unknown"
        mapping = await store.save_external_job_mapping(
            external_job_id=external_job_id,
            run_id=correlation_ids.run_id,
            tool_name=tool_name,
            span_id=span_id,
            status="success",  # Callback arrival usually indicates success
        )
    else:
        # Update status
        callback_status = body.get("status") or "success"
        mapping = await store.update_external_job_status(
            external_job_id=external_job_id,
            status=callback_status,
            callback_received_at=_utc_now(),
        )

    # P0-7: Record span status (note: Langfuse SDK does not support updating existing observation)
    # Actual status is recorded in ExternalJobMapping, which is our primary state source
    if mapping.span_id:
        from backend.app.egb.integrations.langfuse_adapter import LangfuseAdapter
        adapter = LangfuseAdapter()
        if not adapter.initialize():
            logger.warning("LangfuseAdapter: Failed to initialize, span status recorded in ExternalJobMapping only")
        else:
            # Attempt to record status via adapter (note: this does not actually change observation status in Langfuse)
            # Langfuse SDK does not support updating existing observation, status is primarily recorded in ExternalJobMapping
            span_recorded = await adapter.update_span_status(
                trace_id=correlation_ids.run_id,
                span_id=mapping.span_id,
                status=callback_status,
                output=body if body else None,
            )
            if span_recorded:
                logger.info(
                    f"Recorded span {mapping.span_id} status as {callback_status} "
                    f"(note: Langfuse SDK does not support updating existing observation status; "
                    f"actual status is stored in ExternalJobMapping)"
                )
            else:
                logger.info(
                    f"Span {mapping.span_id} status {callback_status} recorded in ExternalJobMapping "
                    f"(Langfuse observation status cannot be updated via SDK)"
                )

    # P0-10: Update run outcome and is_success
    if mapping.run_id:
        # Determine outcome based on callback status
        from backend.app.egb.schemas.run_outcome import RunOutcome
        if callback_status == "success":
            outcome = RunOutcome.SUCCESS.value
        elif callback_status == "failed":
            outcome = RunOutcome.FAILED.value
        elif callback_status == "timeout":
            outcome = RunOutcome.TIMEOUT.value
        else:
            outcome = RunOutcome.PARTIAL.value

        # Update run_index outcome
        await store.update_run_status(
            run_id=mapping.run_id,
            outcome=outcome,
        )
        logger.info(f"Updated run {mapping.run_id} outcome to {outcome}")

    return {
        "status": "received",
        "run_id": correlation_ids.run_id,
        "external_job_id": external_job_id,
        "mapping_status": mapping.status,
        "span_id": mapping.span_id,
    }

