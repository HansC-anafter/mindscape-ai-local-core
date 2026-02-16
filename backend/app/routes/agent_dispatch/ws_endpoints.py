"""
Agent Dispatch — WebSocket endpoint handlers.

Contains the WebSocket endpoints for IDE agent connections and
bridge control channels.
"""

import asyncio
import json
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from .dispatch_manager import get_agent_dispatch_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
#  WebSocket endpoint
# ============================================================


@router.websocket("/ws/agent/{workspace_id}")
async def agent_websocket(
    websocket: WebSocket,
    workspace_id: str,
    client_id: Optional[str] = Query(default=None),
    surface: str = Query(default="gemini_cli"),
):
    """
    WebSocket endpoint for IDE agent connections.

    Connect:  ws://host/ws/agent/{workspace_id}?client_id=xxx&surface=gemini_cli

    Protocol (JSON messages):

    Server → Client:
      - auth_challenge: {type, nonce}
      - dispatch: {type, execution_id, workspace_id, task, ...}
      - pong: {type, ts}
      - result_ack: {type, execution_id}

    Client → Server:
      - auth_response: {type, token, nonce_response}
      - ack: {type, execution_id}
      - progress: {type, execution_id, progress: {percent, message}}
      - result: {type, execution_id, status, output, ...}
      - ping: {type}
    """
    manager = get_agent_dispatch_manager()

    client = await manager.connect(
        websocket=websocket,
        workspace_id=workspace_id,
        client_id=client_id,
        surface_type=surface,
    )

    try:
        # Send auth challenge if auth is enabled
        if not client.authenticated:
            challenge = manager.generate_challenge(client.client_id)
            await websocket.send_text(json.dumps(challenge))
        else:
            # Dev mode — send welcome and flush pending
            flushed = await manager.flush_pending(workspace_id, client)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "welcome",
                        "client_id": client.client_id,
                        "workspace_id": workspace_id,
                        "flushed_tasks": flushed,
                    }
                )
            )

        # Message loop
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "error": "Invalid JSON",
                        }
                    )
                )
                continue

            response = await manager.handle_message(client, data)

            if response:
                await websocket.send_text(json.dumps(response))

            # If auth failed, disconnect
            if response and response.get("type") == "auth_failed":
                await websocket.close(code=4001, reason="Authentication failed")
                break

    except WebSocketDisconnect:
        manager.disconnect(client)
    except Exception as e:
        logger.error(f"[AgentWS] Error for client {client.client_id}: {e}")
        manager.disconnect(client)


# ============================================================
#  Bridge control endpoint (event-driven assignment)
# ============================================================


@router.websocket("/ws/agent/control/{bridge_id}")
async def agent_control_websocket(
    websocket: WebSocket,
    bridge_id: str,
    owner_user_id: Optional[str] = Query(default=None),
):
    """
    Control channel for bridge assignment events.

    Server -> Bridge:
      - welcome: {type, bridge_id, owner_user_id}
      - snapshot: {type, workspace_ids}
      - assign: {type, workspace_id}
      - unassign: {type, workspace_id}
      - pong: {type, ts}

    Bridge -> Server:
      - ping: {type}
    """
    manager = get_agent_dispatch_manager()
    control = await manager.register_control_client(
        websocket=websocket,
        bridge_id=bridge_id,
        owner_user_id=owner_user_id,
    )

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "welcome",
                    "bridge_id": bridge_id,
                    "owner_user_id": owner_user_id,
                }
            )
        )

        # Push current workspace snapshot once on connect.
        try:
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            workspace_ids: List[str] = []
            if owner_user_id:
                workspaces = await asyncio.to_thread(
                    store.list_workspaces,
                    owner_user_id=owner_user_id,
                    primary_project_id=None,
                    limit=200,
                )
                workspace_ids = [ws.id for ws in workspaces if getattr(ws, "id", None)]

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "snapshot",
                        "workspace_ids": workspace_ids,
                    }
                )
            )
        except Exception as e:
            logger.warning(
                f"[AgentWS-Control] Failed to send snapshot to bridge {bridge_id}: {e}"
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "snapshot",
                        "workspace_ids": [],
                    }
                )
            )

        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "ping":
                control.last_heartbeat = time.monotonic()
                await websocket.send_text(
                    json.dumps({"type": "pong", "ts": time.time()})
                )

    except WebSocketDisconnect:
        manager.unregister_control_client(bridge_id)
    except Exception as e:
        logger.error(f"[AgentWS-Control] Error for bridge {bridge_id}: {e}")
        manager.unregister_control_client(bridge_id)
