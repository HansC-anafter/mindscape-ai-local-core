"""Workspace-scoped run harness episode ledger routes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Request

from backend.app.models.run_harness import RunHarnessObservation, RunHarnessResult
from backend.app.models.run_harness_tool_execution import (
    RunHarnessToolExecutionRequest,
)
from backend.app.models.run_harness_workflow_execution import (
    RunHarnessWorkflowExecutionRequest,
)
from backend.app.models.workspace import Workspace
from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.routes.workspace_dependencies import get_store, get_workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.run_harness.episode_ledger import (
    RunHarnessEpisodeLedgerService,
)
from backend.app.services.run_harness.tool_execution_service import (
    RunHarnessToolExecutionService,
)
from backend.app.services.run_harness.workflow_execution_service import (
    RunHarnessWorkflowExecutionService,
)
from backend.app.services.run_harness.product_admission import (
    admit_run_harness_root,
)
from backend.app.services.workspace_capability_admission import (
    AdmissionDenied,
    WorkspaceCapabilityAdmissionFacade,
)
from backend.app.services.workspace_capability_admission.external_execution_adapter import (
    ExternalAuthorizationDenied,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_episode_ledger_service() -> RunHarnessEpisodeLedgerService:
    return RunHarnessEpisodeLedgerService()


def get_tool_execution_service() -> RunHarnessToolExecutionService:
    return RunHarnessToolExecutionService()


def get_workflow_execution_service() -> RunHarnessWorkflowExecutionService:
    return RunHarnessWorkflowExecutionService()


def get_product_admission_facade() -> WorkspaceCapabilityAdmissionFacade:
    return WorkspaceCapabilityAdmissionFacade()


@router.get(
    "/{workspace_id}/run-harness/episodes/{episode_id}",
    response_model=RunHarnessObservation,
)
async def get_run_harness_episode_observation(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    episode_id: str = PathParam(..., description="Run harness episode ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
    service: RunHarnessEpisodeLedgerService = Depends(get_episode_ledger_service),
) -> RunHarnessObservation:
    del workspace, store
    try:
        observation = await asyncio.to_thread(service.get_observation, episode_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to read run harness episode", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if observation is None or observation.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Run harness episode not found")
    return observation


@router.post(
    "/{workspace_id}/run-harness/tools/execute",
    response_model=RunHarnessResult,
)
async def execute_run_harness_tool(
    request: RunHarnessToolExecutionRequest,
    http_request: Request,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
    service: RunHarnessToolExecutionService = Depends(get_tool_execution_service),
    auth: AuthContext = Depends(get_current_user),
    admission_facade: WorkspaceCapabilityAdmissionFacade = Depends(
        get_product_admission_facade
    ),
) -> RunHarnessResult:
    del workspace, store
    if request.envelope.workspace_id != workspace_id:
        raise HTTPException(
            status_code=422,
            detail="Request envelope workspace_id must match route workspace_id",
        )
    try:
        admitted = await admit_run_harness_root(
            request,
            auth=auth,
            remote_ingress_verified=(
                http_request.headers.get("x-mindscape-remote-ingress")
                == "remote_workbench"
            ),
            facade=admission_facade,
        )
        if admitted.external_decision is not None:
            return await service.execute(
                admitted.request,
                external_decision=admitted.external_decision,
                governance_context=admitted.governance_context,
            )
        return await service.execute(
            admitted.request,
            governance_context=admitted.governance_context,
        )
    except (AdmissionDenied, ExternalAuthorizationDenied) as exc:
        raise HTTPException(
            status_code=403,
            detail={"error": exc.code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to execute run harness tool", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/{workspace_id}/run-harness/workflows/start",
    response_model=RunHarnessResult,
)
async def start_run_harness_workflow(
    request: RunHarnessWorkflowExecutionRequest,
    http_request: Request,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
    service: RunHarnessWorkflowExecutionService = Depends(
        get_workflow_execution_service
    ),
    auth: AuthContext = Depends(get_current_user),
    admission_facade: WorkspaceCapabilityAdmissionFacade = Depends(
        get_product_admission_facade
    ),
) -> RunHarnessResult:
    del workspace, store
    if request.workspace_id != workspace_id or request.envelope.workspace_id != workspace_id:
        raise HTTPException(
            status_code=422,
            detail="Request workspace_id must match route workspace_id",
        )
    try:
        admitted = await admit_run_harness_root(
            request,
            auth=auth,
            remote_ingress_verified=(
                http_request.headers.get("x-mindscape-remote-ingress")
                == "remote_workbench"
            ),
            facade=admission_facade,
        )
        if admitted.external_decision is not None:
            return await service.start(
                admitted.request,
                external_decision=admitted.external_decision,
            )
        return await service.start(admitted.request)
    except (AdmissionDenied, ExternalAuthorizationDenied) as exc:
        raise HTTPException(
            status_code=403,
            detail={"error": exc.code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to start run harness workflow", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
