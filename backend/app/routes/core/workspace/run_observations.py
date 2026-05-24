"""Workspace-scoped run observation routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from ....services.run_observation_store import (
    EXTERNAL_RUNNER_SOURCE_KIND,
    RUN_OBSERVATION_STATUSES,
    RunObservationEvent,
    RunObservationStore,
    normalize_observation_status,
)

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_COMPACT_PAYLOAD_BYTES = 16 * 1024


class RunObservationEventRequest(BaseModel):
    run_id: str
    source_kind: str
    provider_code: str
    status: str
    stage_code: str
    summary: str
    idempotency_key: str
    execution_id: Optional[str] = None
    display_title: Optional[str] = None
    stage_index: Optional[int] = None
    stage_total: Optional[int] = None
    prompt_id: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    queue_running: Optional[int] = None
    queue_pending: Optional[int] = None
    artifact_refs: Optional[list[dict[str, Any]]] = None
    progress: Optional[dict[str, Any]] = None
    refs_schema_ref: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def _compact_payload_from_request(
    request: RunObservationEventRequest,
) -> dict[str, Any]:
    payload = dict(request.payload or {})
    payload.setdefault("stage_code", request.stage_code)
    for field_name in (
        "stage_index",
        "stage_total",
        "prompt_id",
        "elapsed_seconds",
        "queue_running",
        "queue_pending",
        "artifact_refs",
        "progress",
        "refs_schema_ref",
    ):
        value = getattr(request, field_name)
        if value is not None:
            payload[field_name] = value
    return payload


def _validate_compact_payload(payload: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid payload: {exc}") from exc
    if len(encoded) > MAX_COMPACT_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Run observation payload is too large")


@router.post("/{workspace_id}/run-observations/events")
async def record_run_observation_event(
    request: RunObservationEventRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> dict[str, Any]:
    """Record one compact external runner observation event."""
    if request.source_kind != EXTERNAL_RUNNER_SOURCE_KIND:
        raise HTTPException(
            status_code=422,
            detail="run-observations/events only accepts source_kind=external_runner",
        )
    payload = _compact_payload_from_request(request)
    status = normalize_observation_status(request.status, payload)
    if status not in RUN_OBSERVATION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported run observation status: {request.status}",
        )
    payload.setdefault("status", status)
    _validate_compact_payload(payload)
    event = RunObservationEvent(
        workspace_id=workspace_id,
        run_id=request.run_id,
        source_kind=request.source_kind,
        provider_code=request.provider_code,
        status=status,
        stage_code=request.stage_code,
        summary=request.summary,
        idempotency_key=request.idempotency_key,
        payload=payload,
        execution_id=request.execution_id,
        display_title=request.display_title,
        occurred_at=request.occurred_at,
        started_at=request.started_at,
        completed_at=request.completed_at,
    )
    try:
        return await asyncio.to_thread(RunObservationStore().record_event, event)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to record run observation", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{workspace_id}/run-observations/summary")
async def get_run_observations_summary(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    active_only: bool = Query(True, description="Return active run cards only"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of cards"),
) -> dict[str, Any]:
    """Return compact external runner summary for one workspace."""
    try:
        return await asyncio.to_thread(
            RunObservationStore().list_summary,
            workspace_id,
            active_only=active_only,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Failed to list run observation summary", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{workspace_id}/run-observations/{run_id}/events")
async def get_run_observation_events(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    run_id: str = PathParam(..., description="Run ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of events"),
) -> dict[str, Any]:
    """Return compact external runner events for one run in one workspace."""
    try:
        return await asyncio.to_thread(
            RunObservationStore().list_events,
            workspace_id,
            run_id,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Failed to list run observation events", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
