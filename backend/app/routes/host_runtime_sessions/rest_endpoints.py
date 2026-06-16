"""Host runtime session REST endpoints."""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.host_runtime_sessions.approval_audit import (
    build_approval_audit_payload,
)
from backend.app.services.host_runtime_sessions.bridge_registry import (
    get_host_runtime_bridge_registry,
)
from backend.app.services.host_runtime_sessions.event_stream import (
    get_host_runtime_event_stream,
)
from backend.app.services.host_runtime_sessions.execution_envelope import (
    GovernanceSnapshotError,
    build_execution_envelope,
)
from backend.app.services.host_runtime_sessions.governance_snapshot import (
    build_governance_refs,
)
from backend.app.services.host_runtime_sessions.models import (
    HostRuntimeEvent,
    HostRuntimeSession,
    HostRuntimeTurn,
    RuntimeSurface,
)
from backend.app.services.host_runtime_sessions.session_store import (
    HostRuntimeSessionStore,
)

router = APIRouter()


class CreateHostRuntimeSessionRequest(BaseModel):
    cwd: str = Field(..., min_length=1)
    runtime_surface: RuntimeSurface = "codex_cli"
    runtime_id: str = "codex_cli"
    actor_id: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StartHostRuntimeTurnRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    context_ref: dict[str, Any] = Field(default_factory=dict)
    intent_ref: dict[str, Any] = Field(default_factory=dict)
    lens_ref: dict[str, Any] = Field(default_factory=dict)
    policy_ref: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolveHostRuntimeApprovalRequest(BaseModel):
    decision: Literal["approved", "denied"]
    actor_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterruptHostRuntimeSessionRequest(BaseModel):
    actor_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def host_runtime_graph_panel_enabled() -> bool:
    value = os.getenv("HOST_RUNTIME_GRAPH_PANEL_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def get_host_runtime_session_store() -> HostRuntimeSessionStore:
    return HostRuntimeSessionStore()


async def _persist_and_publish(store: HostRuntimeSessionStore, event: HostRuntimeEvent) -> HostRuntimeEvent:
    stored_event = store.append_event(event)
    await get_host_runtime_event_stream().publish(stored_event)
    return stored_event


@router.get("/api/v1/host-runtime/status")
async def get_host_runtime_status():
    registry = get_host_runtime_bridge_registry()
    bridges = await registry.snapshots()
    return {
        "enabled": host_runtime_graph_panel_enabled(),
        "runtime_surfaces": ["codex_cli"],
        "bridges": [bridge.model_dump(mode="json") for bridge in bridges],
        "total_bridges": len(bridges),
    }


@router.post("/api/v1/workspaces/{workspace_id}/host-runtime/sessions")
async def create_host_runtime_session(
    workspace_id: str,
    body: CreateHostRuntimeSessionRequest,
):
    if not host_runtime_graph_panel_enabled():
        raise HTTPException(status_code=503, detail="Host runtime graph panel is disabled")

    store = get_host_runtime_session_store()
    session = HostRuntimeSession(
        workspace_id=workspace_id,
        actor_id=body.actor_id,
        runtime_surface=body.runtime_surface,
        runtime_id=body.runtime_id,
        cwd=body.cwd,
        created_by=body.created_by,
        metadata=body.metadata,
        status="ready",
    )
    store.create_session(session)
    await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session.id,
            event_type="session.created",
            payload={
                "runtime_surface": session.runtime_surface,
                "runtime_id": session.runtime_id,
                "cwd": session.cwd,
            },
        ),
    )
    await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session.id,
            event_type="session.ready",
            payload={"status": "ready"},
        ),
    )
    return {"session": session.model_dump(mode="json")}


@router.get("/api/v1/workspaces/{workspace_id}/host-runtime/sessions")
async def list_host_runtime_sessions(
    workspace_id: str,
    limit: int = Query(20, ge=1, le=100),
):
    store = get_host_runtime_session_store()
    sessions = store.list_sessions(workspace_id=workspace_id, limit=limit)
    return {
        "sessions": [session.model_dump(mode="json") for session in sessions],
        "total": len(sessions),
    }


@router.get("/api/v1/workspaces/{workspace_id}/host-runtime/sessions/{session_id}")
async def get_host_runtime_session(workspace_id: str, session_id: str):
    store = get_host_runtime_session_store()
    session = store.get_session(workspace_id=workspace_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Host runtime session not found")
    return {"session": session.model_dump(mode="json")}


@router.get("/api/v1/workspaces/{workspace_id}/host-runtime/sessions/{session_id}/events")
async def list_host_runtime_events(
    workspace_id: str,
    session_id: str,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
):
    store = get_host_runtime_session_store()
    session = store.get_session(workspace_id=workspace_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Host runtime session not found")
    events = store.list_events(
        workspace_id=workspace_id,
        session_id=session_id,
        after_seq=after_seq,
        limit=limit,
    )
    return {
        "workspace_id": workspace_id,
        "session_id": session_id,
        "events": [event.model_dump(mode="json") for event in events],
        "total": len(events),
    }


@router.post("/api/v1/workspaces/{workspace_id}/host-runtime/sessions/{session_id}/turns")
async def start_host_runtime_turn(
    workspace_id: str,
    session_id: str,
    body: StartHostRuntimeTurnRequest,
):
    if not host_runtime_graph_panel_enabled():
        raise HTTPException(status_code=503, detail="Host runtime graph panel is disabled")

    store = get_host_runtime_session_store()
    session = store.get_session(workspace_id=workspace_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Host runtime session not found")

    refs = build_governance_refs(
        workspace_id=workspace_id,
        prompt=body.prompt,
        context_ref=body.context_ref or None,
        intent_ref=body.intent_ref or None,
        lens_ref=body.lens_ref or None,
        policy_ref=body.policy_ref or None,
        artifact_ref=body.artifact_ref or None,
    )
    turn = HostRuntimeTurn(
        session_id=session.id,
        workspace_id=workspace_id,
        status="running",
        prompt_hash=refs["prompt_hash"],
        compiled_prompt_hash=refs["compiled_prompt_hash"],
        intent_ref=refs["intent_ref"],
        lens_ref=refs["lens_ref"],
        policy_ref=refs["policy_ref"],
        context_ref=refs["context_ref"],
        artifact_ref=refs["artifact_ref"],
        governance_trace_ref=refs["governance_trace_ref"],
    )
    try:
        envelope = build_execution_envelope(
            session=session,
            turn=turn,
            prompt=body.prompt,
            context_ref=body.context_ref or None,
            intent_ref=body.intent_ref or None,
            lens_ref=body.lens_ref or None,
            policy_ref=body.policy_ref or None,
            artifact_ref=body.artifact_ref or None,
            metadata=body.metadata,
        )
    except GovernanceSnapshotError as exc:
        turn.status = "governance_blocked"
        store.create_turn(turn)
        event = await _persist_and_publish(
            store,
            HostRuntimeEvent(
                workspace_id=workspace_id,
                session_id=session.id,
                turn_id=turn.id,
                event_type="turn.failed",
                payload={"reason": "governance_blocked", "errors": exc.errors},
            ),
        )
        return {
            "turn": turn.model_dump(mode="json"),
            "status": "governance_blocked",
            "event": event.model_dump(mode="json"),
        }

    store.create_turn(turn)
    await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session.id,
            turn_id=turn.id,
            event_type="governance.snapshot.recorded",
            payload={
                "intent_ref": envelope.intent_ref,
                "lens_ref": envelope.lens_ref,
                "policy_ref": envelope.policy_ref,
                "context_ref": envelope.context_ref,
                "artifact_ref": envelope.artifact_ref,
                "prompt_hash": envelope.prompt_hash,
                "compiled_prompt_hash": envelope.compiled_prompt_hash,
                "governance_trace_ref": envelope.governance_trace_ref,
            },
        ),
    )
    await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session.id,
            turn_id=turn.id,
            event_type="turn.started",
            payload={
                "runtime_surface": session.runtime_surface,
                "runtime_id": session.runtime_id,
                "envelope": envelope.model_dump(mode="json"),
            },
        ),
    )

    registry = get_host_runtime_bridge_registry()
    bridge = await registry.select_bridge(
        workspace_id=workspace_id,
        runtime_surface=session.runtime_surface,
        runtime_id=session.runtime_id,
    )
    if not bridge:
        failed_event = await _persist_and_publish(
            store,
            HostRuntimeEvent(
                workspace_id=workspace_id,
                session_id=session.id,
                turn_id=turn.id,
                event_type="turn.failed",
                payload={"reason": "bridge_unavailable"},
            ),
        )
        store.mark_bridge_unavailable(
            workspace_id=workspace_id,
            session_id=session.id,
            turn_id=turn.id,
        )
        return {
            "turn": turn.model_dump(mode="json"),
            "status": "bridge_unavailable",
            "event": failed_event.model_dump(mode="json"),
        }

    try:
        await registry.dispatch_turn(bridge=bridge, prompt=body.prompt, envelope=envelope)
    except Exception as exc:
        failed_event = await _persist_and_publish(
            store,
            HostRuntimeEvent(
                workspace_id=workspace_id,
                session_id=session.id,
                turn_id=turn.id,
                event_type="turn.failed",
                payload={"reason": "bridge_dispatch_failed", "detail": str(exc)},
            ),
        )
        return {
            "turn": turn.model_dump(mode="json"),
            "status": "bridge_dispatch_failed",
            "event": failed_event.model_dump(mode="json"),
        }

    return {
        "turn": turn.model_dump(mode="json"),
        "status": "accepted",
        "bridge_id": bridge.bridge_id,
        "envelope": envelope.model_dump(mode="json"),
    }


@router.post("/api/v1/workspaces/{workspace_id}/host-runtime/sessions/{session_id}/approvals/{approval_id}")
async def resolve_host_runtime_approval(
    workspace_id: str,
    session_id: str,
    approval_id: str,
    body: ResolveHostRuntimeApprovalRequest,
):
    store = get_host_runtime_session_store()
    session = store.get_session(workspace_id=workspace_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Host runtime session not found")

    payload = build_approval_audit_payload(
        approval_id=approval_id,
        decision=body.decision,
        actor_id=body.actor_id,
        reason=body.reason,
        metadata=body.metadata,
    )
    audit_event = await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session_id,
            turn_id=session.active_turn_id,
            event_type="governance.audit.recorded",
            payload=payload,
        ),
    )
    decision_event = await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session_id,
            turn_id=session.active_turn_id,
            event_type=f"approval.{body.decision}",
            payload=payload,
        ),
    )
    bridge = await get_host_runtime_bridge_registry().select_bridge(
        workspace_id=workspace_id,
        runtime_surface=session.runtime_surface,
        runtime_id=session.runtime_id,
    )
    if bridge:
        async with bridge.send_lock:
            await bridge.websocket.send_json({
                "type": "approval.resolve",
                "workspace_id": workspace_id,
                "session_id": session_id,
                "approval_id": approval_id,
                "decision": body.decision,
                "audit": payload,
            })
    return {
        "audit_event": audit_event.model_dump(mode="json"),
        "decision_event": decision_event.model_dump(mode="json"),
    }


@router.post("/api/v1/workspaces/{workspace_id}/host-runtime/sessions/{session_id}/interrupt")
async def interrupt_host_runtime_session(
    workspace_id: str,
    session_id: str,
    body: InterruptHostRuntimeSessionRequest,
):
    store = get_host_runtime_session_store()
    session = store.get_session(workspace_id=workspace_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Host runtime session not found")
    event = await _persist_and_publish(
        store,
        HostRuntimeEvent(
            workspace_id=workspace_id,
            session_id=session_id,
            turn_id=session.active_turn_id,
            event_type="session.interrupted",
            payload={
                "actor_id": body.actor_id,
                "reason": body.reason,
                "metadata": body.metadata,
            },
        ),
    )
    bridge = await get_host_runtime_bridge_registry().select_bridge(
        workspace_id=workspace_id,
        runtime_surface=session.runtime_surface,
        runtime_id=session.runtime_id,
    )
    if bridge:
        async with bridge.send_lock:
            await bridge.websocket.send_json({
                "type": "session.interrupt",
                "workspace_id": workspace_id,
                "session_id": session_id,
                "reason": body.reason,
            })
    return {"event": event.model_dump(mode="json")}
