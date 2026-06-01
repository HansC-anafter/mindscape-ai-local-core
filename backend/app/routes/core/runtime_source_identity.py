"""Runtime source identity diagnostics."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from backend.app.core.backend_runtime_mode import (
    get_backend_runtime_role,
    should_enable_uvicorn_reload,
)

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


def _module_fingerprint(module_name: str) -> Dict[str, Any]:
    """Return a stable fingerprint for one imported source module."""
    module = __import__(module_name, fromlist=["__name__"])
    source_path = Path(inspect.getfile(module)).resolve()
    data = source_path.read_bytes()
    return {
        "module": module_name,
        "path": str(source_path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def build_runtime_source_identity() -> Dict[str, Any]:
    """Build a dependency-free source identity payload for runtime verification."""
    modules = [
        "backend.app.routes.meeting_sessions",
        "backend.app.routes.core.workspace.meeting_commands",
        "backend.app.services.orchestration.meeting._dispatch_pipeline",
        "backend.app.services.orchestration.meeting.planner_contract_execution.binding_service",
        "backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry",
        "backend.app.services.orchestration.dispatch_orchestrator",
        "backend.app.services.meeting_graph.task_projection",
        "backend.app.services.unified_tool_executor",
    ]
    optional_modules = [
        "backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_models",
        "backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_compiler",
        "backend.app.services.tools.meeting_planner.tool_plan",
    ]
    fingerprints = []
    missing = []
    for module_name in [*modules, *optional_modules]:
        try:
            fingerprints.append(_module_fingerprint(module_name))
        except ModuleNotFoundError:
            missing.append(module_name)
    return {
        "status": "ok",
        "backend_role": get_backend_runtime_role(),
        "reload_enabled": should_enable_uvicorn_reload(),
        "fingerprints": fingerprints,
        "missing_optional_modules": missing,
    }


@router.get("/source-identity")
async def get_runtime_source_identity() -> Dict[str, Any]:
    """Return source fingerprints for meeting full-loop runtime modules."""
    return build_runtime_source_identity()
