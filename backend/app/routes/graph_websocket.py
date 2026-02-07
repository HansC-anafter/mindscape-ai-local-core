"""
Graph WebSocket - Real-time graph change notifications

WebSocket endpoint for broadcasting graph changes to connected clients.
"""

import json
import logging
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected clients per workspace
# workspace_id -> set of WebSocket connections
connected_clients: Dict[str, Set[WebSocket]] = {}


class GraphEventManager:
    """Manages WebSocket connections and event broadcasting"""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, workspace_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        if workspace_id not in self._connections:
            self._connections[workspace_id] = set()
        self._connections[workspace_id].add(websocket)
        logger.info(f"[GraphWS] Client connected to workspace {workspace_id}")

    def disconnect(self, websocket: WebSocket, workspace_id: str):
        """Remove a WebSocket connection"""
        if workspace_id in self._connections:
            self._connections[workspace_id].discard(websocket)
            if not self._connections[workspace_id]:
                del self._connections[workspace_id]
        logger.info(f"[GraphWS] Client disconnected from workspace {workspace_id}")

    async def broadcast(self, workspace_id: str, event: dict):
        """Broadcast an event to all clients in a workspace"""
        if workspace_id not in self._connections:
            return

        message = json.dumps(event)
        disconnected = set()

        for websocket in self._connections[workspace_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(f"[GraphWS] Failed to send to client: {e}")
                disconnected.add(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            self._connections[workspace_id].discard(ws)

    async def notify_change(
        self,
        workspace_id: str,
        event_type: str,  # change_created, change_applied, change_rejected, change_undone
        change_id: str,
        operation: str = "",
        target_type: str = "",
        target_id: str = "",
        actor: str = "",
    ):
        """Send a change notification to all clients"""
        event = {
            "type": event_type,
            "workspace_id": workspace_id,
            "change_id": change_id,
            "operation": operation,
            "target_type": target_type,
            "target_id": target_id,
            "actor": actor,
        }
        await self.broadcast(workspace_id, event)


# Global event manager instance
graph_event_manager = GraphEventManager()


@router.websocket("/ws/graph/{workspace_id}")
async def graph_websocket(websocket: WebSocket, workspace_id: str):
    """
    WebSocket endpoint for graph change notifications.

    Clients connect to receive real-time updates when:
    - New pending changes are created
    - Changes are applied/rejected
    - Changes are undone
    """
    await graph_event_manager.connect(websocket, workspace_id)
    try:
        while True:
            # Keep connection alive, wait for messages (ping/pong handled by FastAPI)
            data = await websocket.receive_text()

            # Handle ping messages from client
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        graph_event_manager.disconnect(websocket, workspace_id)
    except Exception as e:
        logger.error(f"[GraphWS] Error: {e}")
        graph_event_manager.disconnect(websocket, workspace_id)


# Helper function to be called from GraphChangelogStore
async def notify_graph_change(
    workspace_id: str,
    event_type: str,
    change_id: str,
    operation: str = "",
    target_type: str = "",
    target_id: str = "",
    actor: str = "",
):
    """
    Notify all connected clients about a graph change.

    This should be called from GraphChangelogStore when changes occur.
    """
    await graph_event_manager.notify_change(
        workspace_id=workspace_id,
        event_type=event_type,
        change_id=change_id,
        operation=operation,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
    )
