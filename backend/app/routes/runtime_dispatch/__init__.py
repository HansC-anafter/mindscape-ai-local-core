"""Runtime dispatch safety-gate API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.services.runtime_dispatch.contracts import (
    build_dispatch_request_context,
    disabled_dispatch_result,
    not_implemented_dispatch_result,
)
from backend.app.services.runtime_dispatch.feature_gate import (
    get_runtime_dispatch_feature_gate,
    is_runtime_dispatch_enabled,
)
from backend.app.services.runtime_dispatch.metadata import (
    list_runtime_dispatch_selector_types,
    list_runtime_dispatch_targets,
)

router = APIRouter(prefix="/api/v1/runtime-dispatch", tags=["runtime-dispatch"])


def _trace_id_from_request(request: Request) -> str | None:
    return request.headers.get("x-trace-id") or request.headers.get("x-request-id")


@router.get("/feature-gate")
async def get_feature_gate() -> dict[str, object]:
    return {"feature_gate": get_runtime_dispatch_feature_gate()}


@router.get("/selector-types")
async def get_selector_types() -> dict[str, Any]:
    return list_runtime_dispatch_selector_types()


@router.get("/targets")
async def get_targets(
    request: Request,
    workspace_id: str = Query(...),
    source_surface: str | None = Query(None),
    reason: str | None = Query(None),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    context = build_dispatch_request_context(
        current_user,
        workspace_id=workspace_id,
        trace_id=_trace_id_from_request(request),
        source_surface=source_surface,
        reason=reason or "runtime_dispatch_targets",
    )
    payload = list_runtime_dispatch_targets(context.workspace_id)
    payload["context"] = context.to_dict()
    return payload


def _payload_workspace_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("workspace_id") if isinstance(payload, dict) else None
    return str(value).strip() if value is not None and str(value).strip() else None


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key) if isinstance(payload, dict) else None
    return str(value).strip() if value is not None and str(value).strip() else None


async def _mutation_gate_response(
    operation: str,
    *,
    request: Request,
    payload: dict[str, Any],
    current_user: AuthContext,
) -> dict[str, Any]:
    context = build_dispatch_request_context(
        current_user,
        workspace_id=_payload_workspace_id(payload),
        trace_id=_trace_id_from_request(request),
        source_surface=_payload_text(payload, "source_surface"),
        reason=_payload_text(payload, "reason") or f"runtime_dispatch_{operation}",
    )
    if not is_runtime_dispatch_enabled():
        return disabled_dispatch_result(operation, context=context)
    return not_implemented_dispatch_result(operation, context=context)


@router.post("/preview")
async def preview_runtime_dispatch(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    return await _mutation_gate_response(
        "preview",
        request=request,
        payload=payload or {},
        current_user=current_user,
    )


@router.post("/apply")
async def apply_runtime_dispatch(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    return await _mutation_gate_response(
        "apply",
        request=request,
        payload=payload or {},
        current_user=current_user,
    )


@router.post("/repair")
async def repair_runtime_dispatch(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    return await _mutation_gate_response(
        "repair",
        request=request,
        payload=payload or {},
        current_user=current_user,
    )
