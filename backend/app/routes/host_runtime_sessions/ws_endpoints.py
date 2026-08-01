"""Host runtime WebSocket endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.app.services.host_runtime_sessions.bridge_registry import (
    get_host_runtime_bridge_registry,
)
from backend.app.services.host_runtime_sessions.codex_event_mapper import (
    map_codex_app_server_event,
)
from backend.app.services.host_runtime_sessions.event_stream import (
    get_host_runtime_event_stream,
)
from backend.app.services.host_runtime_sessions.models import HostRuntimeEvent
from backend.app.services.host_runtime_sessions.session_store import (
    HostRuntimeSessionStore,
)
from backend.app.services.host_runtime_sessions.connection_lifecycle import (
    close_host_runtime_websocket,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_host_runtime_session_store() -> HostRuntimeSessionStore:
    return HostRuntimeSessionStore()


@router.websocket("/api/v1/workspaces/{workspace_id}/host-runtime/sessions/{session_id}/stream")
async def host_runtime_session_stream(
    websocket: WebSocket,
    workspace_id: str,
    session_id: str,
    last_seq: int = Query(0, ge=0),
):
    await websocket.accept()
    store = get_host_runtime_session_store()
    session = store.get_session(workspace_id=workspace_id, session_id=session_id)
    if not session:
        await websocket.send_json({"type": "error", "detail": "Host runtime session not found"})
        await websocket.close(code=4404)
        await close_host_runtime_websocket(websocket)
        return

    for event in store.list_events(
        workspace_id=workspace_id,
        session_id=session_id,
        after_seq=last_seq,
        limit=1000,
    ):
        await websocket.send_json({"type": "event", "event": event.model_dump(mode="json")})

    stream = get_host_runtime_event_stream()
    try:
        async with stream.subscribe(session_id) as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    await websocket.send_json({"type": "event", "event": event.model_dump(mode="json")})
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        return
    finally:
        await close_host_runtime_websocket(websocket)


@router.websocket("/api/v1/host-runtime/bridge/{bridge_id}")
async def host_runtime_bridge_websocket(
    websocket: WebSocket,
    bridge_id: str,
):
    await websocket.accept()
    registry = get_host_runtime_bridge_registry()
    store = get_host_runtime_session_store()
    stream = get_host_runtime_event_stream()
    await registry.register(bridge_id=bridge_id, websocket=websocket)
    await websocket.send_json({"type": "welcome", "bridge_id": bridge_id})

    try:
        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type") or "")
            if message_type == "register":
                await registry.register(
                    bridge_id=bridge_id,
                    websocket=websocket,
                    runtime_surface=str(message.get("runtime_surface") or "codex_cli"),
                    runtime_id=str(message.get("runtime_id") or "codex_cli"),
                    workspace_ids=[
                        str(item)
                        for item in (message.get("workspace_ids") or [])
                        if str(item).strip()
                    ],
                    capabilities=message.get("capabilities") if isinstance(message.get("capabilities"), dict) else {},
                )
                await websocket.send_json({"type": "registered", "bridge_id": bridge_id})
                continue
            if message_type == "ping":
                await registry.mark_heartbeat(bridge_id)
                await websocket.send_json({"type": "pong"})
                continue
            if message_type != "host_runtime.event":
                await websocket.send_json({"type": "error", "detail": f"Unsupported bridge message: {message_type}"})
                continue

            workspace_id = str(message.get("workspace_id") or "")
            session_id = str(message.get("session_id") or "")
            turn_id = str(message.get("turn_id") or "") or None
            raw_event: dict[str, Any] = message.get("event") if isinstance(message.get("event"), dict) else {}
            mapped = map_codex_app_server_event(raw_event)
            event = HostRuntimeEvent(
                workspace_id=workspace_id,
                session_id=session_id,
                turn_id=turn_id,
                event_type=mapped.event_type,
                item_id=mapped.item_id,
                payload=mapped.payload,
                persist=mapped.persist,
            )
            if mapped.persist:
                event = store.append_event(event)
            await stream.publish(event)
            await websocket.send_json({
                "type": "event_ack",
                "session_id": session_id,
                "turn_id": turn_id,
                "event_type": mapped.event_type,
                "seq": event.seq,
                "persisted": mapped.persist,
            })
    except WebSocketDisconnect:
        await registry.unregister(bridge_id)
    except Exception as exc:
        logger.exception("[HostRuntimeBridge] bridge %s failed", bridge_id)
        await registry.unregister(bridge_id)
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except Exception:
            pass
    finally:
        await registry.unregister(bridge_id)
        await close_host_runtime_websocket(websocket)
