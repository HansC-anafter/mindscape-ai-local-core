"""
Agent Dispatch — Connection lifecycle mixin.

Handles WebSocket client accept, disconnect, heartbeat tracking,
and client lookup by workspace/client ID.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from .models import AgentClient, InflightTask, PendingTask

logger = logging.getLogger(__name__)


class ConnectionMixin:
    """Mixin: IDE agent connection lifecycle management."""

    async def connect(
        self,
        websocket: Any,
        workspace_id: str,
        client_id: Optional[str] = None,
        surface_type: str = "gemini_cli",
    ) -> AgentClient:
        """
        Accept and register a new IDE agent connection.

        Returns the AgentClient after accepting the WebSocket.
        Authentication happens as a separate step via handle_auth().
        """
        await websocket.accept()

        cid = client_id or str(uuid.uuid4())
        client = AgentClient(
            websocket=websocket,
            client_id=cid,
            workspace_id=workspace_id,
            surface_type=surface_type,
        )

        # If auth not required, auto-authenticate (dev mode)
        if not self._auth_required:
            client.authenticated = True

        self._clients[workspace_id][cid] = client

        logger.info(
            f"[AgentWS] Client {cid} ({surface_type}) connected to "
            f"workspace {workspace_id} "
            f"(auth={'skip' if client.authenticated else 'pending'})"
        )

        return client

    def disconnect(self, client: AgentClient) -> None:
        """Remove a client connection and re-queue inflight tasks."""
        ws_id = client.workspace_id
        cid = client.client_id

        if ws_id in self._clients:
            self._clients[ws_id].pop(cid, None)
            if not self._clients[ws_id]:
                del self._clients[ws_id]

        # Re-queue inflight tasks owned by this client
        owned_execs = [
            eid for eid, task in self._inflight.items() if task.client_id == cid
        ]
        for eid in owned_execs:
            task = self._inflight[eid]

            # Skip re-queue if already completed (idempotency guard)
            if eid in self._completed:
                self._inflight.pop(eid)
                logger.info(f"[AgentWS] Skipping re-queue for completed task {eid}")
                if task.result_future and not task.result_future.done():
                    task.result_future.set_result(
                        {
                            "execution_id": eid,
                            "status": "completed",
                            "output": "Already completed before disconnect",
                        }
                    )
                continue

            # Re-queue with payload if available.
            # KEEP the inflight entry alive (set client_id='pending')
            # so flush_pending can reconnect the original result_future.
            if task.payload:
                task.client_id = "pending"  # mark as awaiting re-dispatch
                pending = PendingTask(
                    execution_id=eid,
                    workspace_id=ws_id,
                    payload=task.payload,
                    attempts=1,  # count disconnect as one attempt
                )
                self._enqueue_pending(pending)
                logger.warning(
                    f"[AgentWS] Re-queued task {eid} after client {cid} disconnect "
                    f"(result_future preserved)"
                )
            else:
                # No payload to re-queue — fail the future and remove inflight
                self._inflight.pop(eid)
                if task.result_future and not task.result_future.done():
                    task.result_future.set_result(
                        {
                            "execution_id": eid,
                            "status": "failed",
                            "error": f"Client {cid} disconnected, no payload to re-queue",
                        }
                    )
                logger.warning(f"[AgentWS] Cannot re-queue task {eid} (no payload)")

        logger.info(f"[AgentWS] Client {cid} disconnected from workspace {ws_id}")

    def has_connections(self, workspace_id: Optional[str] = None) -> bool:
        """Check if there are any authenticated connections."""
        if workspace_id:
            clients = self._clients.get(workspace_id, {})
            return any(c.authenticated for c in clients.values())
        return any(
            c.authenticated
            for ws_clients in self._clients.values()
            for c in ws_clients.values()
        )

    def get_connected_workspaces(self) -> List[str]:
        """Return list of workspace IDs that have authenticated clients."""
        return [
            ws_id
            for ws_id, clients in self._clients.items()
            if any(c.authenticated for c in clients.values())
        ]

    def get_client(
        self,
        workspace_id: str,
        client_id: Optional[str] = None,
    ) -> Optional[AgentClient]:
        """
        Get a specific client, or the best available client for a workspace.

        If client_id is specified, returns that exact client.
        Otherwise, returns the most recently active authenticated client.
        """
        ws_clients = self._clients.get(workspace_id, {})

        if client_id:
            client = ws_clients.get(client_id)
            if client and client.authenticated:
                return client
            return None

        # Find best available: most recent heartbeat
        authenticated = [c for c in ws_clients.values() if c.authenticated]
        if not authenticated:
            return None

        return max(authenticated, key=lambda c: c.last_heartbeat)
