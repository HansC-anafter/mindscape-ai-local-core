"""Unified model-route registry for the Settings page."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database.session import get_db_postgres as get_db
from backend.app.services.executor_routing_policy_service import (
    ExecutorRoutingPolicyService,
)
from backend.app.services.model_routing_policy_service import ModelRoutingPolicyService
from backend.app.services.model_route_slot_registry import ModelRouteSlotRegistry

router = APIRouter(prefix="/api/v1/settings/model-route-registry", tags=["settings"])


class WorkspaceExecutorRouteUpdateRequest(BaseModel):
    workspace_id: str = Field(..., description="Workspace ID")
    executor_runtime: Optional[str] = Field(
        default=None,
        description="Primary executor runtime override for this workspace",
    )


class WorkspaceExecutorSurfaceBindingRequest(BaseModel):
    workspace_id: str = Field(..., description="Workspace ID")
    surface: str = Field(..., description="Executor runtime surface, e.g. codex_cli")
    preferred_runtime_id: Optional[str] = Field(
        default=None,
        description="Preferred concrete runtime id for the surface",
    )


@router.get("")
def get_model_route_registry(
    installed_only: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    registry = ModelRouteSlotRegistry()
    payload = registry.collect_inventory(db=db, installed_only=installed_only)
    payload["policy"] = ModelRoutingPolicyService().build_policy_summary()
    payload["executor_policy"] = ExecutorRoutingPolicyService().build_registry_summary()
    return payload


@router.post("/reconcile")
def reconcile_model_route_registry(
    installed_only: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    registry = ModelRouteSlotRegistry()
    pack_result = registry.reconcile_installed_pack_registrations(
        installed_only=installed_only
    )
    runtime_result = registry.reconcile_runtime_registrations(db=db)
    return {
        **pack_result,
        **runtime_result,
    }


@router.get("/workspace-chat")
def get_workspace_chat_route(
    workspace_id: Optional[str] = None,
    profile_id: str = "default-user",
) -> Dict[str, Any]:
    return ModelRoutingPolicyService().build_workspace_chat_payload(
        workspace_id=workspace_id,
        profile_id=profile_id,
    )


@router.put("/local-core/chat-default")
def update_local_core_chat_default(
    model_name: str,
    provider: str = "openai",
    api_key_setting_key: Optional[str] = None,
) -> Dict[str, Any]:
    return ModelRoutingPolicyService().update_chat_default(
        model_name=model_name,
        provider=provider,
        api_key_setting_key=api_key_setting_key,
    )


@router.get("/workspace-executor")
def get_workspace_executor_route(
    workspace_id: str,
) -> Dict[str, Any]:
    return ExecutorRoutingPolicyService().build_workspace_executor_payload(workspace_id)


@router.put("/workspace-executor")
def update_workspace_executor_route(
    request: WorkspaceExecutorRouteUpdateRequest = Body(...),
) -> Dict[str, Any]:
    return ExecutorRoutingPolicyService().set_workspace_primary_runtime(
        workspace_id=request.workspace_id,
        executor_runtime=request.executor_runtime,
    )


@router.put("/workspace-executor/preferred-runtime")
def update_workspace_executor_preferred_runtime(
    request: WorkspaceExecutorSurfaceBindingRequest = Body(...),
) -> Dict[str, Any]:
    return ExecutorRoutingPolicyService().set_workspace_surface_preferred_runtime(
        workspace_id=request.workspace_id,
        surface=request.surface,
        preferred_runtime_id=request.preferred_runtime_id,
    )
