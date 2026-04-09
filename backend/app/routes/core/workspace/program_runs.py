import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.orchestration.meeting.program_runtime_adapter import (
    build_program_run_summary,
)
from backend.app.services.stores.program_run_store import ProgramRunStore

logger = logging.getLogger(__name__)

router = APIRouter()


class ProgramRunSummaryResponse(BaseModel):
    id: str
    meeting_session_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    status: str
    source: str
    scale: Optional[str] = None
    workstream_count: int = 0
    milestone_count: int = 0
    target_outputs: List[str] = Field(default_factory=list)
    remaining_work_count: int = 0
    completed_work_count: int = 0
    failed_work_count: int = 0
    recorded_at: Optional[str] = None


class ProgramRunDetailResponse(ProgramRunSummaryResponse):
    program_spec: Dict[str, Any] = Field(default_factory=dict)
    cursor_state: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProgramRunListResponse(BaseModel):
    program_runs: List[ProgramRunSummaryResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


def _to_summary_response(program_run) -> ProgramRunSummaryResponse:
    summary = build_program_run_summary(program_run)
    return ProgramRunSummaryResponse(
        **summary,
        project_id=program_run.project_id,
        thread_id=program_run.thread_id,
    )


def _to_detail_response(program_run) -> ProgramRunDetailResponse:
    summary = build_program_run_summary(program_run)
    return ProgramRunDetailResponse(
        **summary,
        project_id=program_run.project_id,
        thread_id=program_run.thread_id,
        program_spec=dict(program_run.program_spec or {}),
        cursor_state=dict(program_run.cursor_state or {}),
        metadata=dict(program_run.metadata or {}),
        created_at=program_run.created_at.isoformat() if program_run.created_at else None,
        updated_at=program_run.updated_at.isoformat() if program_run.updated_at else None,
    )


@router.get(
    "/{workspace_id}/program-runs",
    response_model=ProgramRunListResponse,
)
async def list_workspace_program_runs(
    workspace_id: str,
    project_id: Optional[str] = Query(None),
    meeting_session_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: Workspace = Depends(get_workspace),
) -> ProgramRunListResponse:
    store = ProgramRunStore()
    runs = store.list_by_workspace(
        workspace.id,
        project_id=project_id,
        meeting_session_id=meeting_session_id,
        limit=limit,
        offset=offset,
    )
    return ProgramRunListResponse(
        program_runs=[_to_summary_response(program_run) for program_run in runs],
        total=len(runs),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{workspace_id}/program-runs/{program_run_id}",
    response_model=ProgramRunDetailResponse,
)
async def get_workspace_program_run(
    workspace_id: str,
    program_run_id: str,
    workspace: Workspace = Depends(get_workspace),
) -> ProgramRunDetailResponse:
    store = ProgramRunStore()
    program_run = store.get_by_id(program_run_id)
    if not program_run:
        raise HTTPException(status_code=404, detail="Program run not found")
    if program_run.workspace_id != workspace.id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    return _to_detail_response(program_run)
