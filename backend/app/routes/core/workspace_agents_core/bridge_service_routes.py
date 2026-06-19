"""Workspace-scoped CLI bridge service routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Path as PathParam

from backend.app.services.external_agents.cli_bridge_service_control import (
    get_cli_bridge_service_status,
)

router = APIRouter()


@router.get("/bridge-service")
async def get_workspace_agent_bridge_service(
    workspace_id: str = PathParam(..., description="Workspace ID"),
):
    return await get_cli_bridge_service_status("status")


@router.post("/bridge-service/start")
async def start_workspace_agent_bridge_service(
    workspace_id: str = PathParam(..., description="Workspace ID"),
):
    return await get_cli_bridge_service_status("start")


@router.post("/bridge-service/restart")
async def restart_workspace_agent_bridge_service(
    workspace_id: str = PathParam(..., description="Workspace ID"),
):
    return await get_cli_bridge_service_status("restart")
