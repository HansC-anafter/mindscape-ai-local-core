"""
Tool execution routes

Provides unified tool execution interface for Playbook integration.
Supports builtin, langchain, and MCP tools.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel
from uuid import uuid4

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.services.unified_tool_executor import UnifiedToolExecutor, ToolExecutionResult
from backend.app.services.playbook_tool_resolver import ToolDependencyResolver
from backend.app.services.workspace_capability_admission import (
    AdmissionDenied,
    RootAdmissionRequest,
    WorkspaceCapabilityAdmissionFacade,
)
from backend.app.services.workspace_capability_admission.external_execution_adapter import (
    ExternalAuthorizationDenied,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    build_verified_tool_execution_context,
)
from backend.app.routes.core.execution_dispatch import (
    build_external_authorization_context,
    dispatch_remote_execution,
)
from backend.app.models.playbook import ToolDependency
from .base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])
admission_facade = WorkspaceCapabilityAdmissionFacade()


def get_tool_executor() -> UnifiedToolExecutor:
    """
    Get UnifiedToolExecutor instance
    """
    return UnifiedToolExecutor()


def get_tool_resolver() -> ToolDependencyResolver:
    """
    Get ToolDependencyResolver instance
    """
    return ToolDependencyResolver()


class ToolExecutionScope(BaseModel):
    workspace_id: str
    product_surface_id: str
    active_group_id: Optional[str] = None
    observed_topology_revision: Optional[int] = None
    operation_type: Literal[
        "query",
        "read",
        "generate",
        "modify",
        "delete",
        "publish",
        "payment",
    ] = "modify"
    execution_backend: Literal["local", "external_provider"] = "local"
    trace_id: Optional[str] = None
    root_execution_id: Optional[str] = None


class ExecuteToolRequest(ToolExecutionScope):
    """Request to execute a tool"""
    tool_name: str
    arguments: Dict[str, Any]
    timeout: Optional[float] = 30.0


class ExecuteToolDependencyRequest(ToolExecutionScope):
    """Request to execute a tool dependency"""
    tool_dependency: ToolDependency
    arguments: Dict[str, Any]
    env_overrides: Optional[Dict[str, str]] = None


@router.post("/execute", response_model=Dict[str, Any])
async def execute_tool(
    request: ExecuteToolRequest,
    http_request: Request,
    profile_id: str = Query(..., description="Profile ID"),
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
    auth: AuthContext = Depends(get_current_user),
):
    """
    Execute a tool (unified interface for Playbook)

    Supports multiple tool types:
    - builtin: wordpress, notion, etc.
    - langchain: langchain.wikipedia, etc.
    - mcp: mcp.github.search_issues, etc.

    Args:
        request: Tool execution request
        profile_id: Profile ID
        executor: Unified tool executor

    Returns:
        Tool execution result

    Example:
        POST /api/v1/tools/execute?profile_id=user123
        {
            "tool_name": "wordpress.list_posts",
            "arguments": {"per_page": 10}
        }
    """
    try:
        root_execution_id = (
            request.root_execution_id or f"tool-{uuid4().hex}"
        )
        admission = await admission_facade.admit_root(
            RootAdmissionRequest(
                workspace_id=request.workspace_id,
                explicit_active_group_id=request.active_group_id,
                observed_topology_revision=(
                    request.observed_topology_revision
                ),
                product_surface_id=request.product_surface_id,
                selector_kind="tool",
                selector_key=request.tool_name,
                operation_type=request.operation_type,
                entry=(
                    "remote"
                    if http_request.headers.get(
                        "x-mindscape-remote-ingress"
                    ) == "remote_workbench"
                    else "local"
                ),
                remote_ingress_verified=(
                    http_request.headers.get(
                        "x-mindscape-remote-ingress"
                    ) == "remote_workbench"
                ),
                execution_backend=request.execution_backend,
                actor_user_id=auth.user_id,
                allowed_workspace_ids=auth.workspace_ids,
                allowed_group_ids=auth.group_ids,
                trace_id=request.trace_id or root_execution_id,
                root_execution_id=root_execution_id,
            )
        )
        governed_arguments = {
            **request.arguments,
            "execution_admission_snapshot": (
                admission.snapshot.model_dump(mode="json")
            ),
            "root_execution_id": root_execution_id,
        }
        if request.execution_backend == "external_provider":
            return await dispatch_remote_execution(
                playbook_code=request.tool_name,
                inputs=governed_arguments,
                workspace_id=request.workspace_id,
                profile_id=profile_id,
                execution_id=root_execution_id,
                trace_id=request.trace_id or root_execution_id,
                remote_job_type="tool",
                remote_request_payload={
                    "tool_name": request.tool_name,
                    "inputs": request.arguments,
                },
                external_authorization_context=(
                    build_external_authorization_context(
                        admission.external_decision
                    )
                ),
            )
        result = await executor.execute_tool(
            tool_name=request.tool_name,
            arguments=governed_arguments,
            timeout=request.timeout,
            governance_context=build_verified_tool_execution_context(admission),
        )
        result.metadata = {
            **(result.metadata or {}),
            "admission_snapshot_hash": (
                admission.snapshot.snapshot_hash
            ),
        }
        return result.to_dict()
    except AdmissionDenied as e:
        raise_api_error(403, f"Tool execution denied: {e.code}")
    except ExternalAuthorizationDenied as e:
        raise_api_error(403, f"Tool execution denied: {e.code}")
    except Exception as e:
        raise_api_error(500, f"Tool execution failed: {str(e)}")


@router.post("/execute-dependency", response_model=Dict[str, Any])
async def execute_tool_dependency(
    request: ExecuteToolDependencyRequest,
    http_request: Request,
    profile_id: str = Query(..., description="Profile ID"),
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
    auth: AuthContext = Depends(get_current_user),
):
    """
    Execute a tool dependency (from Playbook configuration)

    Automatically handles:
    - Environment variable substitution
    - Tool lookup
    - Fallback mechanism

    Args:
        request: Tool dependency execution request
        profile_id: Profile ID
        executor: Unified tool executor

    Returns:
        Tool execution result
    """
    try:
        root_execution_id = (
            request.root_execution_id or f"tool-{uuid4().hex}"
        )
        admission = await admission_facade.admit_root(
            RootAdmissionRequest(
                workspace_id=request.workspace_id,
                explicit_active_group_id=request.active_group_id,
                observed_topology_revision=(
                    request.observed_topology_revision
                ),
                product_surface_id=request.product_surface_id,
                selector_kind="tool",
                selector_key=request.tool_dependency.name,
                operation_type=request.operation_type,
                entry=(
                    "remote"
                    if http_request.headers.get(
                        "x-mindscape-remote-ingress"
                    ) == "remote_workbench"
                    else "local"
                ),
                remote_ingress_verified=(
                    http_request.headers.get(
                        "x-mindscape-remote-ingress"
                    ) == "remote_workbench"
                ),
                execution_backend=request.execution_backend,
                actor_user_id=auth.user_id,
                allowed_workspace_ids=auth.workspace_ids,
                allowed_group_ids=auth.group_ids,
                trace_id=request.trace_id or root_execution_id,
                root_execution_id=root_execution_id,
            )
        )
        governed_arguments = {
            **request.arguments,
            "execution_admission_snapshot": (
                admission.snapshot.model_dump(mode="json")
            ),
            "root_execution_id": root_execution_id,
            "workspace_id": request.workspace_id,
        }
        if request.execution_backend == "external_provider":
            return await dispatch_remote_execution(
                playbook_code=request.tool_dependency.name,
                inputs=governed_arguments,
                workspace_id=request.workspace_id,
                profile_id=profile_id,
                execution_id=root_execution_id,
                trace_id=request.trace_id or root_execution_id,
                remote_job_type="tool",
                remote_request_payload={
                    "tool_dependency": request.tool_dependency.model_dump(
                        mode="json"
                    ),
                    "inputs": request.arguments,
                },
                external_authorization_context=(
                    build_external_authorization_context(
                        admission.external_decision
                    )
                ),
            )
        result = await executor.execute_tool_dependency(
            tool_dep=request.tool_dependency,
            arguments=governed_arguments,
            env_overrides=request.env_overrides
        )
        result.metadata = {
            **(result.metadata or {}),
            "admission_snapshot_hash": (
                admission.snapshot.snapshot_hash
            ),
        }
        return result.to_dict()
    except AdmissionDenied as e:
        raise_api_error(403, f"Tool execution denied: {e.code}")
    except ExternalAuthorizationDenied as e:
        raise_api_error(403, f"Tool execution denied: {e.code}")
    except Exception as e:
        raise_api_error(500, f"Tool dependency execution failed: {str(e)}")


@router.post("/check-dependencies", response_model=Dict[str, Any])
async def check_tool_dependencies(
    tool_dependencies: List[ToolDependency],
    profile_id: str = Query(..., description="Profile ID"),
    resolver: ToolDependencyResolver = Depends(get_tool_resolver),
):
    """
    Check tool dependencies for Playbook

    Args:
        tool_dependencies: List of tool dependencies
        profile_id: Profile ID
        resolver: Tool dependency resolver

    Returns:
        Dependency check result with availability status
    """
    try:
        result = await resolver.resolve_dependencies(tool_dependencies)
        return result
    except Exception as e:
        raise_api_error(500, f"Dependency check failed: {str(e)}")


@router.post("/auto-install", response_model=Dict[str, Any])
async def auto_install_tool(
    tool_dep: ToolDependency,
    profile_id: str = Query(..., description="Profile ID"),
    resolver: ToolDependencyResolver = Depends(get_tool_resolver),
):
    """
    Auto-install a tool if possible

    Supports:
    - langchain tools: Auto-install via pip
    - mcp tools: Connect to MCP server

    Args:
        tool_dep: Tool dependency to install
        profile_id: Profile ID
        resolver: Tool dependency resolver

    Returns:
        Installation result
    """
    try:
        result = await resolver.auto_install_tool(tool_dep)
        return result
    except Exception as e:
        raise_api_error(500, f"Auto-install failed: {str(e)}")


@router.get("/execution-history", response_model=List[Dict[str, Any]])
async def get_execution_history(
    limit: Optional[int] = Query(None, description="Limit number of results"),
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
):
    """
    Get tool execution history

    Args:
        limit: Limit number of results
        executor: Unified tool executor

    Returns:
        List of execution history records
    """
    try:
        history = executor.get_execution_history(limit=limit)
        return history
    except Exception as e:
        raise_api_error(500, f"Failed to get execution history: {str(e)}")


@router.get("/execution-statistics", response_model=Dict[str, Any])
async def get_execution_statistics(
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
):
    """
    Get tool execution statistics

    Returns:
        Execution statistics (success rate, avg time, etc.)
    """
    try:
        stats = executor.get_statistics()
        return stats
    except Exception as e:
        raise_api_error(500, f"Failed to get statistics: {str(e)}")
