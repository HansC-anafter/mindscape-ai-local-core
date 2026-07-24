"""Thin HTTP root seam before capability lazy activation."""

from __future__ import annotations

import json
import re
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.app.dependencies.auth import get_current_user
from backend.app.services.workspace_capability_admission import (
    AdmissionDenied,
    RootAdmissionRequest,
    WorkspaceCapabilityAdmissionFacade,
)
from backend.app.services.workspace_capability_admission.external_execution_adapter import (
    ExternalAuthorizationDenied,
)


_CAPABILITY_PREFIX = "/api/v1/capabilities/"
_ROOT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_WORKSPACE_PATH = re.compile(r"/workspaces/([^/]+)")
_facade = WorkspaceCapabilityAdmissionFacade()


def _operation_type(request: Request) -> str:
    explicit = request.headers.get("x-mindscape-operation-type")
    if explicit:
        return explicit
    if request.method == "DELETE":
        return "delete"
    if request.method in {"PUT", "PATCH"}:
        return "modify"
    path = request.url.path.lower()
    if any(token in path for token in ("publish", "post", "send")):
        return "publish"
    if any(token in path for token in ("generate", "render", "analyze")):
        return "generate"
    return "modify"


async def _json_body_workspace_id(request: Request) -> str | None:
    content_type = request.headers.get("content-type", "")
    content_length = request.headers.get("content-length", "")
    if "application/json" not in content_type:
        return None
    try:
        if content_length and int(content_length) > 64 * 1024:
            return None
    except ValueError:
        return None
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    candidates = [
        payload.get("workspace_id"),
        (payload.get("context") or {}).get("workspace_id")
        if isinstance(payload.get("context"), dict)
        else None,
        (payload.get("input") or {}).get("workspace_id")
        if isinstance(payload.get("input"), dict)
        else None,
    ]
    return next(
        (
            value.strip()
            for value in candidates
            if isinstance(value, str) and value.strip()
        ),
        None,
    )


async def _workspace_id(request: Request) -> str | None:
    header = request.headers.get("x-workspace-id")
    if header and header.strip():
        return header.strip()
    query = request.query_params.get("workspace_id")
    if query and query.strip():
        return query.strip()
    match = _WORKSPACE_PATH.search(request.url.path)
    if match:
        return match.group(1)
    return await _json_body_workspace_id(request)


def _is_root_candidate(request: Request) -> bool:
    if not request.url.path.startswith(_CAPABILITY_PREFIX):
        return False
    return (
        request.method in _ROOT_METHODS
        or request.headers.get("x-mindscape-admission-root") == "1"
    )


async def admit_workspace_capability_request(
    request: Request,
) -> JSONResponse | None:
    """Admit a discoverable workspace root or leave non-root/history traffic alone."""
    if not _is_root_candidate(request):
        return None
    workspace_id = await _workspace_id(request)
    if workspace_id is None:
        return None
    auth = await get_current_user(request)
    request.state.mindscape_auth_context = auth
    root_execution_id = (
        request.headers.get("x-root-execution-id")
        or f"http-{uuid4().hex}"
    )
    trace_id = request.headers.get("x-trace-id") or root_execution_id
    group_id = (
        request.headers.get("x-active-workspace-group-id")
        or request.query_params.get("active_group_id")
    )
    revision_raw = (
        request.headers.get("x-workspace-group-revision")
        or request.query_params.get("observed_topology_revision")
    )
    try:
        revision = int(revision_raw) if revision_raw else None
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"detail": "workspace_group_revision_invalid"},
        )
    try:
        result = await _facade.admit_root(
            RootAdmissionRequest(
                workspace_id=workspace_id,
                explicit_active_group_id=group_id,
                observed_topology_revision=revision,
                product_surface_id=request.headers.get(
                    "x-product-surface-id"
                ),
                selector_kind="api_prefix",
                selector_key=request.url.path,
                operation_type=_operation_type(request),
                entry=(
                    "remote"
                    if request.headers.get("x-mindscape-remote-ingress")
                    == "remote_workbench"
                    else "local"
                ),
                remote_ingress_verified=(
                    request.headers.get("x-mindscape-remote-ingress")
                    == "remote_workbench"
                ),
                execution_backend=request.headers.get(
                    "x-mindscape-execution-backend",
                    "local",
                ),
                actor_user_id=auth.user_id,
                allowed_workspace_ids=auth.workspace_ids,
                allowed_group_ids=auth.group_ids,
                trace_id=trace_id,
                root_execution_id=root_execution_id,
            )
        )
    except AdmissionDenied as exc:
        return JSONResponse(
            status_code=403,
            content={"detail": {"error": exc.code}},
        )
    except ExternalAuthorizationDenied as exc:
        return JSONResponse(
            status_code=403,
            content={"detail": {"error": exc.code}},
        )
    request.state.execution_admission_snapshot = result.snapshot
    request.state.external_execution_decision = result.external_decision
    return None

