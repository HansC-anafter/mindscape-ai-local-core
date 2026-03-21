"""
Remote execution terminal callback routes.

Cloud / remote executors report terminal execution state back to local-core
through this ingress. Success cases are delegated to GovernanceEngine so the
existing completion pipeline remains the single source of truth.
"""

import os
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.orchestration.governance_engine import GovernanceEngine

router = APIRouter(prefix="/api/v1/executions", tags=["remote-execution"])


class RemoteTerminalEventRequest(BaseModel):
    tenant_id: str
    workspace_id: str
    execution_id: str
    trace_id: str
    status: str
    job_type: Optional[Literal["playbook", "tool", "chain"]] = None
    capability_code: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    playbook_code: Optional[str] = None
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)


def _authorize_remote_callback(
    authorization: Optional[str],
    callback_secret: Optional[str],
) -> None:
    expected = (os.getenv("LOCAL_CORE_REMOTE_CALLBACK_SECRET") or "").strip()
    if not expected:
        return

    bearer_token = ""
    if isinstance(authorization, str) and authorization.lower().startswith("bearer "):
        bearer_token = authorization[7:].strip()
    provided = callback_secret or bearer_token
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid remote callback secret")


@router.post("/remote-terminal-events")
async def remote_terminal_event_callback(
    body: RemoteTerminalEventRequest,
    authorization: Optional[str] = Header(None),
    x_callback_secret: Optional[str] = Header(None),
):
    """Receive remote terminal events and bridge them into governed completion."""
    _authorize_remote_callback(authorization, x_callback_secret)

    governance = GovernanceEngine()
    result = governance.process_remote_terminal_event(
        tenant_id=body.tenant_id,
        workspace_id=body.workspace_id,
        execution_id=body.execution_id,
        trace_id=body.trace_id,
        status=body.status,
        result_payload=body.result_payload,
        error_message=body.error_message,
        job_type=body.job_type,
        capability_code=body.capability_code,
        playbook_code=body.playbook_code,
        provider_metadata=body.provider_metadata,
    )

    if result.get("error_code") == "EXECUTION_SHELL_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Execution shell not found")
    if result.get("error", "").startswith("unsupported remote terminal status"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result
