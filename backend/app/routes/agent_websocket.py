"""
Agent WebSocket — Real-time task dispatch to IDE agents

WebSocket endpoint for dispatching coding tasks to Antigravity and other
IDE-based agents. Supports authentication, multi-client routing, heartbeat,
and a pending queue for disconnected clients.

Endpoint: /ws/agent/{workspace_id}
Protocol: JSON messages with 'type' field (auth, dispatch, ack, progress, result, ping, pong)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Query,
    Body,
    HTTPException,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
#  Data types
# ============================================================


@dataclass
class AgentClient:
    """Represents a connected IDE agent client."""

    websocket: WebSocket
    client_id: str
    workspace_id: str
    surface_type: str  # e.g. "antigravity", "cursor", "windsurf"
    connected_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    authenticated: bool = False


@dataclass
class PendingTask:
    """A task waiting to be dispatched to an IDE client."""

    execution_id: str
    workspace_id: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.monotonic)
    target_client_id: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3


@dataclass
class InflightTask:
    """A task currently being executed by an IDE client."""

    execution_id: str
    workspace_id: str
    client_id: str
    dispatched_at: float = field(default_factory=time.monotonic)
    acked: bool = False
    result_future: Optional[asyncio.Future] = None


# ============================================================
#  AgentDispatchManager
# ============================================================


class AgentDispatchManager:
    """
    Manages WebSocket connections from IDE agents and task dispatch.

    Responsibilities:
      - Accept and authenticate IDE connections
      - Track connected clients per workspace
      - Dispatch tasks to specific or any available client
      - Maintain a pending queue for offline clients
      - Track inflight tasks and resolve futures on result
      - Heartbeat monitoring

    Security:
      - Token-based authentication on connect
      - HMAC nonce challenge-response
      - Per-workspace client isolation
    """

    # Heartbeat interval (seconds)
    HEARTBEAT_INTERVAL: float = 30.0

    # Client timeout — mark as dead if no heartbeat after this
    CLIENT_TIMEOUT: float = 90.0

    # Auth timeout — client must authenticate within this window
    AUTH_TIMEOUT: float = 10.0

    # Max pending queue size per workspace
    MAX_PENDING_QUEUE: int = 100

    def __init__(self, auth_secret: Optional[str] = None):
        """
        Initialize dispatch manager.

        Args:
            auth_secret: HMAC secret for nonce authentication.
                         If None, auth is skipped (dev mode).
        """
        self.auth_secret = auth_secret

        # workspace_id -> {client_id -> AgentClient}
        self._clients: Dict[str, Dict[str, AgentClient]] = defaultdict(dict)

        # workspace_id -> [PendingTask]
        self._pending_queue: Dict[str, List[PendingTask]] = defaultdict(list)

        # execution_id -> InflightTask
        self._inflight: Dict[str, InflightTask] = {}

        # execution_id -> nonce (for auth challenges)
        self._nonces: Dict[str, str] = {}

    # ============================================================
    #  Connection lifecycle
    # ============================================================

    async def connect(
        self,
        websocket: WebSocket,
        workspace_id: str,
        client_id: Optional[str] = None,
        surface_type: str = "antigravity",
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

        # If no auth_secret, auto-authenticate (dev mode)
        if not self.auth_secret:
            client.authenticated = True

        self._clients[workspace_id][cid] = client

        logger.info(
            f"[AgentWS] Client {cid} ({surface_type}) connected to "
            f"workspace {workspace_id} "
            f"(auth={'skip' if client.authenticated else 'pending'})"
        )

        return client

    def disconnect(self, client: AgentClient) -> None:
        """Remove a client connection and clean up inflight tasks."""
        ws_id = client.workspace_id
        cid = client.client_id

        if ws_id in self._clients:
            self._clients[ws_id].pop(cid, None)
            if not self._clients[ws_id]:
                del self._clients[ws_id]

        # Fail any inflight tasks owned by this client
        failed_execs = [
            eid for eid, task in self._inflight.items() if task.client_id == cid
        ]
        for eid in failed_execs:
            task = self._inflight.pop(eid)
            if task.result_future and not task.result_future.done():
                task.result_future.set_result(
                    {
                        "execution_id": eid,
                        "status": "failed",
                        "error": f"Client {cid} disconnected during execution",
                    }
                )
            # Re-queue the task for retry
            logger.warning(f"[AgentWS] Re-queuing task {eid} after client disconnect")

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

    # ============================================================
    #  Authentication
    # ============================================================

    def generate_challenge(self, client_id: str) -> Dict[str, str]:
        """Generate a nonce challenge for client authentication."""
        nonce = secrets.token_hex(32)
        self._nonces[client_id] = nonce
        return {
            "type": "auth_challenge",
            "nonce": nonce,
        }

    def verify_auth(
        self,
        client_id: str,
        token: str,
        nonce_response: str,
    ) -> bool:
        """
        Verify client authentication.

        The client must provide:
          - token: a pre-shared agent token
          - nonce_response: HMAC-SHA256(auth_secret, nonce + client_id)
        """
        if not self.auth_secret:
            return True  # Dev mode — skip auth

        expected_nonce = self._nonces.pop(client_id, None)
        if not expected_nonce:
            logger.warning(f"[AgentWS] No pending nonce for client {client_id}")
            return False

        # Verify HMAC
        expected_hmac = hmac.new(
            self.auth_secret.encode(),
            (expected_nonce + client_id).encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(nonce_response, expected_hmac):
            logger.warning(f"[AgentWS] HMAC mismatch for client {client_id}")
            return False

        return True

    # ============================================================
    #  Task dispatch
    # ============================================================

    async def dispatch_and_wait(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        target_client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch a task to an IDE client and wait for the result.

        If no client is available, queues the task for later pickup.

        Args:
            workspace_id: Target workspace
            message: Dispatch message payload
            execution_id: Unique execution ID
            target_client_id: Optional specific client to target

        Returns:
            Raw result dict from the IDE

        Raises:
            asyncio.CancelledError: If the wait is cancelled
        """
        loop = asyncio.get_event_loop()
        result_future: asyncio.Future = loop.create_future()

        client = self.get_client(workspace_id, target_client_id)

        if client:
            # Direct dispatch via WebSocket
            inflight = InflightTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                client_id=client.client_id,
                result_future=result_future,
            )
            self._inflight[execution_id] = inflight

            try:
                await client.websocket.send_text(json.dumps(message))
                logger.info(
                    f"[AgentWS] Dispatched {execution_id} to "
                    f"client {client.client_id}"
                )
            except Exception as e:
                self._inflight.pop(execution_id, None)
                result_future.set_result(
                    {
                        "execution_id": execution_id,
                        "status": "failed",
                        "error": f"Failed to send dispatch: {e}",
                    }
                )
        else:
            # No client available — queue for later
            pending = PendingTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                payload=message,
                target_client_id=target_client_id,
            )
            self._enqueue_pending(pending)

            # Create inflight entry that will be resolved when
            # a client picks up and completes the task
            inflight = InflightTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                client_id="pending",
                result_future=result_future,
            )
            self._inflight[execution_id] = inflight

            logger.info(
                f"[AgentWS] No client available for {workspace_id}, "
                f"queued task {execution_id}"
            )

        return await result_future

    def _enqueue_pending(self, task: PendingTask) -> None:
        """Add a task to the pending queue, respecting max size."""
        queue = self._pending_queue[task.workspace_id]
        if len(queue) >= self.MAX_PENDING_QUEUE:
            # Drop oldest
            dropped = queue.pop(0)
            logger.warning(
                f"[AgentWS] Pending queue full for {task.workspace_id}, "
                f"dropping oldest task {dropped.execution_id}"
            )
        queue.append(task)

    async def flush_pending(self, workspace_id: str, client: AgentClient) -> int:
        """
        Send all pending tasks for a workspace to a newly connected client.

        Returns the number of tasks flushed.
        """
        queue = self._pending_queue.get(workspace_id, [])
        if not queue:
            return 0

        flushed = 0
        remaining = []

        for task in queue:
            # Skip if targeted to a different client
            if task.target_client_id and task.target_client_id != client.client_id:
                remaining.append(task)
                continue

            task.attempts += 1
            if task.attempts > task.max_attempts:
                # Give up on this task
                inflight = self._inflight.pop(task.execution_id, None)
                if (
                    inflight
                    and inflight.result_future
                    and not inflight.result_future.done()
                ):
                    inflight.result_future.set_result(
                        {
                            "execution_id": task.execution_id,
                            "status": "failed",
                            "error": f"Max dispatch attempts ({task.max_attempts}) exceeded",
                        }
                    )
                continue

            try:
                await client.websocket.send_text(json.dumps(task.payload))

                # Update inflight to point to this client
                if task.execution_id in self._inflight:
                    self._inflight[task.execution_id].client_id = client.client_id
                    self._inflight[task.execution_id].dispatched_at = time.monotonic()

                flushed += 1
                logger.info(
                    f"[AgentWS] Flushed pending task {task.execution_id} "
                    f"to client {client.client_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[AgentWS] Failed to flush task {task.execution_id}: {e}"
                )
                remaining.append(task)

        self._pending_queue[workspace_id] = remaining

        if flushed:
            logger.info(
                f"[AgentWS] Flushed {flushed} pending tasks to "
                f"client {client.client_id} in workspace {workspace_id}"
            )

        return flushed

    # ============================================================
    #  Message handling
    # ============================================================

    async def handle_message(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Handle an incoming message from an IDE client.

        Message types:
          - auth_response: Client authentication response
          - ack: Task acknowledged by client
          - progress: Task progress update
          - result: Task execution result
          - ping: Heartbeat ping

        Returns an optional response message to send back.
        """
        msg_type = data.get("type", "")

        if msg_type == "auth_response":
            return await self._handle_auth_response(client, data)

        # All other messages require authentication
        if not client.authenticated:
            return {
                "type": "error",
                "error": "Not authenticated",
                "code": "AUTH_REQUIRED",
            }

        if msg_type == "ack":
            return self._handle_ack(client, data)
        elif msg_type == "progress":
            return self._handle_progress(client, data)
        elif msg_type == "result":
            return self._handle_result(client, data)
        elif msg_type == "ping":
            client.last_heartbeat = time.monotonic()
            return {"type": "pong", "ts": time.time()}
        else:
            logger.warning(
                f"[AgentWS] Unknown message type '{msg_type}' "
                f"from client {client.client_id}"
            )
            return None

    async def _handle_auth_response(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process client authentication response."""
        token = data.get("token", "")
        nonce_response = data.get("nonce_response", "")

        if self.verify_auth(client.client_id, token, nonce_response):
            client.authenticated = True
            logger.info(f"[AgentWS] Client {client.client_id} authenticated")

            # Flush any pending tasks
            flushed = await self.flush_pending(
                client.workspace_id,
                client,
            )

            return {
                "type": "auth_ok",
                "client_id": client.client_id,
                "flushed_tasks": flushed,
            }
        else:
            logger.warning(f"[AgentWS] Client {client.client_id} auth failed")
            return {
                "type": "auth_failed",
                "error": "Authentication failed",
            }

    def _handle_ack(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle task acknowledgment from IDE."""
        execution_id = data.get("execution_id", "")
        inflight = self._inflight.get(execution_id)

        if not inflight:
            logger.warning(f"[AgentWS] ACK for unknown execution {execution_id}")
            return None

        inflight.acked = True
        logger.info(
            f"[AgentWS] Task {execution_id} acknowledged by "
            f"client {client.client_id}"
        )
        return None

    def _handle_progress(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle progress update from IDE."""
        execution_id = data.get("execution_id", "")
        progress = data.get("progress", {})

        inflight = self._inflight.get(execution_id)
        if not inflight:
            logger.warning(f"[AgentWS] Progress for unknown execution {execution_id}")
            return None

        logger.debug(
            f"[AgentWS] Progress for {execution_id}: "
            f"{progress.get('percent', '?')}% - {progress.get('message', '')}"
        )
        # Progress could be forwarded to the UI via graph_websocket or SSE
        return None

    def _handle_result(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Handle task execution result from IDE.

        Resolves the Future for dispatch_and_wait callers.
        """
        execution_id = data.get("execution_id", "")
        inflight = self._inflight.pop(execution_id, None)

        if not inflight:
            logger.warning(
                f"[AgentWS] Result for unknown/completed execution {execution_id}"
            )
            return None

        # Build result dict
        result = {
            "execution_id": execution_id,
            "status": data.get("status", "completed"),
            "output": data.get("output", ""),
            "duration_seconds": data.get("duration_seconds", 0),
            "tool_calls": data.get("tool_calls", []),
            "files_modified": data.get("files_modified", []),
            "files_created": data.get("files_created", []),
            "error": data.get("error"),
            "governance": data.get("governance", {}),
            "metadata": {
                "transport": "ws_push",
                "client_id": client.client_id,
                "surface_type": client.surface_type,
            },
        }

        # Resolve the future
        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)

        logger.info(
            f"[AgentWS] Result received for {execution_id}: "
            f"status={data.get('status', 'unknown')}"
        )

        return {
            "type": "result_ack",
            "execution_id": execution_id,
        }

    # ============================================================
    #  REST fallback: pending tasks + result submit
    # ============================================================

    def get_pending_tasks(
        self,
        workspace_id: str,
        surface_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get pending tasks for a workspace (REST polling endpoint).

        Returns task payloads without removing them from the queue.
        """
        queue = self._pending_queue.get(workspace_id, [])
        return [t.payload for t in queue]

    def submit_result(
        self,
        execution_id: str,
        result_data: Dict[str, Any],
    ) -> bool:
        """
        Submit a task result via REST (for polling fallback).

        Returns True if the result was accepted.
        """
        inflight = self._inflight.pop(execution_id, None)

        if inflight and inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result_data)
            logger.info(f"[AgentWS] REST result submitted for {execution_id}")
            return True

        # Check pending queue
        for ws_id, queue in self._pending_queue.items():
            for i, task in enumerate(queue):
                if task.execution_id == execution_id:
                    queue.pop(i)
                    logger.info(
                        f"[AgentWS] REST result for pending task {execution_id}"
                    )
                    return True

        logger.warning(f"[AgentWS] REST result for unknown execution {execution_id}")
        return False

    # ============================================================
    #  Status / diagnostics
    # ============================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current dispatch manager status."""
        return {
            "connected_workspaces": len(self._clients),
            "total_clients": sum(len(clients) for clients in self._clients.values()),
            "authenticated_clients": sum(
                sum(1 for c in clients.values() if c.authenticated)
                for clients in self._clients.values()
            ),
            "inflight_tasks": len(self._inflight),
            "pending_tasks": sum(len(q) for q in self._pending_queue.values()),
            "workspaces": {
                ws_id: {
                    "clients": [
                        {
                            "client_id": c.client_id,
                            "surface_type": c.surface_type,
                            "authenticated": c.authenticated,
                        }
                        for c in clients.values()
                    ],
                    "pending_count": len(self._pending_queue.get(ws_id, [])),
                }
                for ws_id, clients in self._clients.items()
            },
        }


# ============================================================
#  Global singleton
# ============================================================

agent_dispatch_manager = AgentDispatchManager()


def get_agent_dispatch_manager() -> AgentDispatchManager:
    """Get the global dispatch manager singleton."""
    return agent_dispatch_manager


# ============================================================
#  WebSocket endpoint
# ============================================================


@router.websocket("/ws/agent/{workspace_id}")
async def agent_websocket(
    websocket: WebSocket,
    workspace_id: str,
    client_id: Optional[str] = Query(default=None),
    surface: str = Query(default="antigravity"),
):
    """
    WebSocket endpoint for IDE agent connections.

    Connect:  ws://host/ws/agent/{workspace_id}?client_id=xxx&surface=antigravity

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
#  REST endpoints (polling fallback + result submit)
# ============================================================


from fastapi import HTTPException
from pydantic import BaseModel, Field


class AgentResultRequest(BaseModel):
    """Request body for submitting agent execution results."""

    execution_id: str = Field(..., description="Execution ID")
    status: str = Field(
        default="completed",
        description="Execution status: completed | failed",
    )
    output: str = Field(default="", description="Execution output/summary")
    duration_seconds: float = Field(default=0, description="Duration in seconds")
    tool_calls: list = Field(default_factory=list, description="Tools invoked")
    files_modified: list = Field(
        default_factory=list,
        description="Files modified during execution",
    )
    files_created: list = Field(
        default_factory=list,
        description="Files created during execution",
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    governance: dict = Field(
        default_factory=dict,
        description="Governance trace (output_hash, summary, etc.)",
    )


class AgentResultResponse(BaseModel):
    """Response for agent result submission."""

    accepted: bool
    execution_id: str
    message: str = ""


@router.get("/api/v1/mcp/agent/pending")
async def get_pending_tasks(
    workspace_id: str = Query(..., description="Workspace ID"),
    surface: str = Query(default="antigravity", description="Surface type"),
):
    """
    REST polling endpoint — get pending tasks for the IDE to pick up.

    Used as fallback when WebSocket is unavailable.
    """
    manager = get_agent_dispatch_manager()
    tasks = manager.get_pending_tasks(workspace_id, surface)
    return {
        "tasks": tasks,
        "count": len(tasks),
        "workspace_id": workspace_id,
    }


@router.post("/api/v1/mcp/agent/result", response_model=AgentResultResponse)
async def submit_agent_result(body: AgentResultRequest):
    """
    Unified result submission endpoint.

    Accepts results regardless of transport (WS or Polling).
    The IDE calls this endpoint to report task completion.
    """
    manager = get_agent_dispatch_manager()

    result_data = body.model_dump()
    result_data["metadata"] = {"transport": "rest_submit"}

    accepted = manager.submit_result(body.execution_id, result_data)

    if not accepted:
        raise HTTPException(
            status_code=404,
            detail=f"No pending or inflight task with execution_id={body.execution_id}",
        )

    return AgentResultResponse(
        accepted=True,
        execution_id=body.execution_id,
        message="Result accepted",
    )


@router.get("/api/v1/mcp/agent/status")
async def get_dispatch_status():
    """Get current dispatch manager status (diagnostic endpoint)."""
    manager = get_agent_dispatch_manager()
    return manager.get_status()
