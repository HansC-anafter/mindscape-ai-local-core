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
import os
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Set

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
class AgentControlClient:
    """Represents a connected bridge control client."""

    websocket: WebSocket
    bridge_id: str
    owner_user_id: Optional[str] = None
    connected_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)


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
    payload: Optional[Dict[str, Any]] = None  # retained for re-queue on disconnect


@dataclass
class ReservedTask:
    """A task reserved by a polling client with lease timeout."""

    task: PendingTask
    client_id: str
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reserved_at: float = field(default_factory=time.monotonic)
    lease_seconds: float = 30.0
    acked: bool = False
    cumulative_lease: float = 0.0

    # Max cumulative lease per task (30 minutes)
    MAX_CUMULATIVE_LEASE: ClassVar[float] = 1800.0

    @property
    def lease_deadline(self) -> float:
        return self.reserved_at + self.lease_seconds

    @property
    def expired(self) -> bool:
        return time.monotonic() > self.lease_deadline

    def extend_lease(self, seconds: float) -> bool:
        """Extend lease. Returns False if cumulative cap exceeded."""
        if self.cumulative_lease + seconds > self.MAX_CUMULATIVE_LEASE:
            return False
        self.lease_seconds += seconds
        self.cumulative_lease += seconds
        return True

    def reset_lease(self, seconds: float) -> bool:
        """Reset lease timer from now. Returns False if cap exceeded."""
        now = time.monotonic()
        elapsed = now - self.reserved_at
        new_total = elapsed + seconds
        if self.cumulative_lease + seconds > self.MAX_CUMULATIVE_LEASE:
            return False
        self.lease_seconds = new_total
        self.cumulative_lease += seconds
        return True


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

    # Max completed execution IDs to track for idempotency
    COMPLETED_MAX_SIZE: int = 1000

    def __init__(
        self,
        auth_secret: Optional[str] = None,
        expected_token: Optional[str] = None,
    ):
        """
        Initialize dispatch manager.

        Args:
            auth_secret: HMAC secret for nonce authentication.
            expected_token: Pre-shared agent token.

        Security semantics:
            Both None  -> dev mode (fail-open, auto-authenticate)
            Either set -> prod mode (fail-closed, verify both)
        """
        self.auth_secret = auth_secret
        self._expected_token = expected_token
        self._auth_required = bool(auth_secret or expected_token)

        # workspace_id -> {client_id -> AgentClient}
        self._clients: Dict[str, Dict[str, AgentClient]] = defaultdict(dict)

        # workspace_id -> [PendingTask]
        self._pending_queue: Dict[str, List[PendingTask]] = defaultdict(list)

        # execution_id -> InflightTask
        self._inflight: Dict[str, InflightTask] = {}

        # execution_id -> nonce (for auth challenges)
        self._nonces: Dict[str, str] = {}

        # Completed execution IDs — OrderedDict for FIFO eviction
        self._completed: OrderedDict = OrderedDict()

        # execution_id -> ReservedTask (for REST polling lease)
        self._reserved: Dict[str, ReservedTask] = {}

        # workspace_id -> asyncio.Event (signaled when a task is enqueued)
        self._task_events: Dict[str, asyncio.Event] = defaultdict(asyncio.Event)

        # bridge_id -> AgentControlClient (control channel for event-driven assignment)
        self._bridge_controls: Dict[str, AgentControlClient] = {}

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

    # ============================================================
    #  Bridge control channel (event-driven workspace assignment)
    # ============================================================

    async def register_control_client(
        self,
        websocket: WebSocket,
        bridge_id: str,
        owner_user_id: Optional[str] = None,
    ) -> AgentControlClient:
        """Accept and register a bridge control WebSocket."""
        await websocket.accept()
        control = AgentControlClient(
            websocket=websocket,
            bridge_id=bridge_id,
            owner_user_id=owner_user_id,
        )
        self._bridge_controls[bridge_id] = control
        logger.info(
            f"[AgentWS-Control] Bridge {bridge_id} connected "
            f"(owner_user_id={owner_user_id or 'any'})"
        )
        return control

    def unregister_control_client(self, bridge_id: str) -> None:
        """Unregister a bridge control WebSocket."""
        if bridge_id in self._bridge_controls:
            self._bridge_controls.pop(bridge_id, None)
            logger.info(f"[AgentWS-Control] Bridge {bridge_id} disconnected")

    async def _send_control_message(
        self,
        control: AgentControlClient,
        message: Dict[str, Any],
    ) -> bool:
        """Send a control message. Returns False when send fails."""
        try:
            await control.websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.warning(
                f"[AgentWS-Control] Failed to send to bridge {control.bridge_id}: {e}"
            )
            self.unregister_control_client(control.bridge_id)
            return False

    async def broadcast_workspace_assign(
        self,
        workspace_id: str,
        owner_user_id: Optional[str] = None,
    ) -> int:
        """
        Push assign event to matching bridges.

        If owner_user_id is provided, only bridges with the same owner receive it.
        """
        sent = 0
        for control in list(self._bridge_controls.values()):
            if (
                owner_user_id
                and control.owner_user_id
                and control.owner_user_id != owner_user_id
            ):
                continue
            ok = await self._send_control_message(
                control,
                {
                    "type": "assign",
                    "workspace_id": workspace_id,
                },
            )
            if ok:
                sent += 1
        return sent

    async def broadcast_workspace_unassign(
        self,
        workspace_id: str,
        owner_user_id: Optional[str] = None,
    ) -> int:
        """Push unassign event to matching bridges."""
        sent = 0
        for control in list(self._bridge_controls.values()):
            if (
                owner_user_id
                and control.owner_user_id
                and control.owner_user_id != owner_user_id
            ):
                continue
            ok = await self._send_control_message(
                control,
                {
                    "type": "unassign",
                    "workspace_id": workspace_id,
                },
            )
            if ok:
                sent += 1
        return sent

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

        Security:
          - Both secrets None = dev mode (fail-open)
          - Either set = prod mode (fail-closed, both verified)
        """
        if not self._auth_required:
            return True  # Dev mode — both secrets empty

        # Verify pre-shared token
        if not self._expected_token or not token:
            logger.warning(f"[AgentWS] Token missing for client {client_id}")
            return False
        if not hmac.compare_digest(token, self._expected_token):
            logger.warning(f"[AgentWS] Invalid token for client {client_id}")
            return False

        # Verify HMAC nonce
        if not self.auth_secret:
            logger.warning(
                f"[AgentWS] auth_secret missing, cannot verify HMAC "
                f"for client {client_id}"
            )
            return False

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
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """
        Dispatch a task to an IDE client and wait for the result.

        If no client is available, queues the task for later pickup.

        Args:
            workspace_id: Target workspace
            message: Dispatch message payload
            execution_id: Unique execution ID
            target_client_id: Optional specific client to target
            timeout: Max seconds to wait for result (default 120s)

        Returns:
            Raw result dict from the IDE
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
                payload=message,  # retain for re-queue on disconnect
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
                payload=message,  # retain for re-queue
            )
            self._inflight[execution_id] = inflight

            logger.info(
                f"[AgentWS] No client available for {workspace_id}, "
                f"queued task {execution_id}"
            )

        try:
            return await asyncio.wait_for(result_future, timeout=timeout)
        except asyncio.TimeoutError:
            self._inflight.pop(execution_id, None)
            logger.error(
                f"[AgentWS] dispatch_and_wait timed out for {execution_id} "
                f"after {timeout}s"
            )
            return {
                "execution_id": execution_id,
                "status": "timeout",
                "error": f"No result received within {timeout}s",
            }

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

        # Wake any long-polling clients waiting for this workspace
        event = self._task_events.get(task.workspace_id)
        if event:
            event.set()

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

    # ============================================================
    #  Ownership verification
    # ============================================================

    def _verify_ownership(
        self,
        client: AgentClient,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Check client owns the inflight task.

        Returns error dict if ownership fails, None if verified.
        """
        inflight = self._inflight.get(execution_id)
        if not inflight:
            return {
                "type": "error",
                "error": f"Unknown execution {execution_id}",
            }
        if inflight.client_id != client.client_id:
            logger.warning(
                f"[AgentWS] Unauthorized: expected={inflight.client_id}, "
                f"got={client.client_id} for {execution_id}"
            )
            return {
                "type": "error",
                "error": "Not the assigned client",
            }
        return None  # ownership verified

    def _handle_ack(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle task acknowledgment from IDE."""
        execution_id = data.get("execution_id", "")

        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        inflight = self._inflight[execution_id]
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

        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        progress = data.get("progress", {})
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

        # Check ownership before popping (use get first)
        err = self._verify_ownership(client, execution_id)
        if err:
            return err

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

        # Track completion for idempotency (prevents duplicate re-queue)
        self._completed[execution_id] = time.monotonic()
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)  # FIFO eviction

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

    def reserve_pending_tasks(
        self,
        workspace_id: str,
        client_id: str,
        surface_type: Optional[str] = None,
        limit: int = 5,
        lease_seconds: float = 60.0,
    ) -> List[Dict[str, Any]]:
        """
        Atomic reserve: pending tasks with lease timeout (REST polling).

        Tasks are atomically moved from queue to _reserved with lease_id.
        If the client crashes (lease expires), tasks auto-return to queue.
        Respects target_client_id filtering on PendingTask.
        """
        # Lazy reclaim expired leases before reserving new ones
        self._reclaim_expired_reserves()

        queue = self._pending_queue.get(workspace_id, [])
        reserved, remaining = [], []

        for t in queue:
            # Skip if targeted to a different client
            if t.target_client_id and t.target_client_id != client_id:
                remaining.append(t)
                continue

            if len(reserved) < limit:
                r = ReservedTask(
                    task=t,
                    client_id=client_id,
                    reserved_at=time.monotonic(),
                    lease_seconds=lease_seconds,
                )
                self._reserved[t.execution_id] = r
                reserved.append(r)
            else:
                remaining.append(t)

        self._pending_queue[workspace_id] = remaining

        if reserved:
            logger.info(
                f"[AgentWS] Reserved {len(reserved)} tasks for "
                f"client {client_id} in workspace {workspace_id}"
            )

        # Return payload + lease_id for each reserved task
        results = []
        for r in reserved:
            payload = dict(r.task.payload)
            payload["lease_id"] = r.lease_id
            results.append(payload)
        return results

    def _reclaim_expired_reserves(self) -> None:
        """Return expired reserved tasks back to the pending queue."""
        for eid, r in list(self._reserved.items()):
            if r.expired:
                self._reserved.pop(eid)
                self._enqueue_pending(r.task)
                logger.warning(f"[AgentWS] Lease expired for {eid}, re-queued")

    def ack_task(
        self,
        execution_id: str,
        lease_id: str,
        client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Acknowledge task pickup and extend lease (30s -> 300s).

        Verifies lease_id to prevent ghost duplicate execution.
        Idempotent: re-acking same task+lease returns same result.
        Returns lease info dict or None if rejected.
        """
        reserved = self._reserved.get(execution_id)
        if not reserved:
            # Idempotent: already completed?
            if execution_id in self._completed:
                return {"execution_id": execution_id, "status": "already_completed"}
            return None

        # Verify lease_id
        if reserved.lease_id != lease_id:
            logger.warning(
                f"[AgentWS] ack lease_id mismatch for {execution_id}: "
                f"expected {reserved.lease_id}, got {lease_id}"
            )
            return None

        # Verify client ownership
        if client_id and reserved.client_id != client_id:
            logger.warning(
                f"[AgentWS] ack client mismatch for {execution_id}: "
                f"reserved by {reserved.client_id}, acked by {client_id}"
            )
            return None

        # Idempotent: already acked
        if reserved.acked:
            return {
                "execution_id": execution_id,
                "lease_id": lease_id,
                "lease_expires_at": reserved.lease_deadline,
                "status": "already_acked",
            }

        # Extend lease and mark acked
        reserved.acked = True
        reserved.extend_lease(270.0)  # 30s initial + 270s = 300s total
        logger.info(f"[AgentWS] Task {execution_id} acked, lease extended to 300s")

        return {
            "execution_id": execution_id,
            "lease_id": lease_id,
            "lease_expires_at": reserved.lease_deadline,
            "status": "acked",
        }

    def report_progress(
        self,
        execution_id: str,
        lease_id: str,
        progress_pct: Optional[float] = None,
        message: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Report task progress and reset lease timer.

        Verifies lease_id. Idempotent: duplicate calls just update timestamp.
        Returns False if lease cap (30min) exceeded.
        """
        reserved = self._reserved.get(execution_id)
        if not reserved:
            return None

        if reserved.lease_id != lease_id:
            return None
        if client_id and reserved.client_id != client_id:
            return None

        # Reset lease timer (120s from now)
        if not reserved.reset_lease(120.0):
            logger.warning(
                f"[AgentWS] Lease cap exceeded for {execution_id}, "
                f"cumulative={reserved.cumulative_lease:.0f}s"
            )
            return {
                "execution_id": execution_id,
                "status": "lease_cap_exceeded",
                "cumulative_lease": reserved.cumulative_lease,
            }

        return {
            "execution_id": execution_id,
            "lease_expires_at": reserved.lease_deadline,
            "progress_pct": progress_pct,
            "status": "ok",
        }

    def list_inflight(
        self,
        client_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List tasks currently reserved/inflight for a specific client.

        Used for crash recovery: runner restarts and picks up where it left off.
        """
        self._reclaim_expired_reserves()
        results = []
        for eid, r in self._reserved.items():
            if r.client_id == client_id:
                payload = dict(r.task.payload)
                payload["lease_id"] = r.lease_id
                payload["acked"] = r.acked
                payload["lease_expires_at"] = r.lease_deadline
                results.append(payload)
        return results

    def submit_result(
        self,
        execution_id: str,
        result_data: Dict[str, Any],
        client_id: Optional[str] = None,
        lease_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Submit a task result via REST.

        Verifies lease_id when provided. Idempotent: second call = no-op.
        Returns context dict on success (with workspace_id for landing),
        or None on rejection.
        """
        # Idempotent: already completed
        if execution_id in self._completed:
            logger.info(f"[AgentWS] Duplicate submit for {execution_id}, no-op")
            return {"accepted": True, "duplicate": True}

        # Check reserved tasks first
        reserved = self._reserved.get(execution_id)
        if reserved:
            # Verify lease_id if provided
            if lease_id and reserved.lease_id != lease_id:
                logger.warning(
                    f"[AgentWS] submit_result lease_id mismatch for {execution_id}"
                )
                return None
            # Verify client ownership
            if client_id and reserved.client_id != client_id:
                logger.warning(
                    f"[AgentWS] submit_result client mismatch for {execution_id}"
                )
                return None

            # Capture context before popping
            workspace_id = reserved.task.workspace_id
            task_payload = dict(reserved.task.payload)

            self._reserved.pop(execution_id)
            inflight = self._inflight.pop(execution_id, None)
            if (
                inflight
                and inflight.result_future
                and not inflight.result_future.done()
            ):
                inflight.result_future.set_result(result_data)
            self._completed[execution_id] = time.monotonic()
            while len(self._completed) > self.COMPLETED_MAX_SIZE:
                self._completed.popitem(last=False)
            logger.info(
                f"[AgentWS] REST result submitted for reserved task {execution_id}"
            )
            return {
                "accepted": True,
                "workspace_id": workspace_id,
                "task_id": task_payload.get("task_id"),
                "thread_id": task_payload.get("thread_id"),
                "project_id": task_payload.get("project_id"),
            }

        # Check inflight tasks
        inflight = self._inflight.pop(execution_id, None)
        if inflight and inflight.result_future and not inflight.result_future.done():
            workspace_id = inflight.workspace_id
            inflight.result_future.set_result(result_data)
            self._completed[execution_id] = time.monotonic()
            while len(self._completed) > self.COMPLETED_MAX_SIZE:
                self._completed.popitem(last=False)
            logger.info(f"[AgentWS] REST result submitted for {execution_id}")
            return {
                "accepted": True,
                "workspace_id": workspace_id,
                "task_id": (inflight.payload or {}).get("task_id"),
                "thread_id": (inflight.payload or {}).get("thread_id"),
                "project_id": (inflight.payload or {}).get("project_id"),
            }

        # Check pending queue
        for ws_id, queue in self._pending_queue.items():
            for i, task in enumerate(queue):
                if task.execution_id == execution_id:
                    workspace_id = task.workspace_id
                    task_payload = dict(task.payload)
                    queue.pop(i)
                    self._completed[execution_id] = time.monotonic()
                    logger.info(
                        f"[AgentWS] REST result for pending task {execution_id}"
                    )
                    return {
                        "accepted": True,
                        "workspace_id": workspace_id,
                        "task_id": task_payload.get("task_id"),
                        "thread_id": task_payload.get("thread_id"),
                        "project_id": task_payload.get("project_id"),
                    }

        logger.warning(f"[AgentWS] REST result for unknown execution {execution_id}")
        return None

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
            "bridge_controls": len(self._bridge_controls),
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
            "bridges": [
                {
                    "bridge_id": b.bridge_id,
                    "owner_user_id": b.owner_user_id,
                }
                for b in self._bridge_controls.values()
            ],
        }


# ============================================================
#  Global singleton
# ============================================================

agent_dispatch_manager = AgentDispatchManager(
    auth_secret=os.environ.get("AGENT_AUTH_SECRET"),
    expected_token=os.environ.get("AGENT_TOKEN"),
)


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
    output: str = Field(
        default="", description="Human-readable summary (max 500 chars)"
    )
    result_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured result payload for persistence",
    )
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Files to persist with the result [{filename, content, encoding?}]",
    )
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
    client_id: Optional[str] = Field(
        default=None,
        description="Client ID for ownership verification on reserved tasks",
    )
    lease_id: Optional[str] = Field(
        default=None,
        description="Lease ID for ownership verification",
    )
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
async def reserve_pending_tasks_endpoint(
    workspace_id: str = Query(..., description="Workspace ID"),
    client_id: str = Query(..., description="Client ID for lease tracking"),
    surface: str = Query(default="antigravity", description="Surface type"),
    limit: int = Query(default=5, ge=1, le=20, description="Max tasks to reserve"),
    lease_seconds: float = Query(
        default=60.0, ge=10, le=300, description="Lease duration"
    ),
    wait_seconds: float = Query(
        default=0,
        ge=0,
        le=5,
        description="Long-poll wait time (max 5s to avoid MCP host timeout).",
    ),
):
    """
    REST long-poll endpoint for MCP pull-based task runner.

    When wait_seconds > 0 and the queue is empty, the request blocks
    until a task is enqueued or the timeout expires. This enables
    protocol-level guardian mode without client-side busy polling.
    """
    manager = get_agent_dispatch_manager()
    tasks = manager.reserve_pending_tasks(
        workspace_id=workspace_id,
        client_id=client_id,
        surface_type=surface,
        limit=limit,
        lease_seconds=lease_seconds,
    )

    # Long-poll: if no tasks and wait_seconds > 0, block until signaled
    if not tasks and wait_seconds > 0:
        event = manager._task_events[workspace_id]
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            pass
        # Re-check queue after wake-up
        tasks = manager.reserve_pending_tasks(
            workspace_id=workspace_id,
            client_id=client_id,
            surface_type=surface,
            limit=limit,
            lease_seconds=lease_seconds,
        )

    return {"tasks": tasks, "count": len(tasks)}


@router.post("/api/v1/mcp/agent/result", response_model=AgentResultResponse)
async def submit_agent_result(body: AgentResultRequest):
    """
    Submit task execution result via REST.

    Used by MCP Gateway's mindscape_task_submit_result tool.
    Handles both reserved (lease) and inflight tasks.
    After accepting, persists result to workspace filesystem + DB (best-effort).
    """
    manager = get_agent_dispatch_manager()
    result_data = body.model_dump(exclude={"execution_id", "client_id", "lease_id"})
    ctx = manager.submit_result(
        execution_id=body.execution_id,
        result_data=result_data,
        client_id=body.client_id,
        lease_id=body.lease_id,
    )
    if ctx is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending/inflight task found for execution_id={body.execution_id}",
        )

    # Best-effort: persist result to workspace filesystem + DB
    if not ctx.get("duplicate"):
        try:
            from app.services.task_result_landing import TaskResultLandingService
            from app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            workspace_id = ctx.get("workspace_id")
            if workspace_id:
                ws_store = PostgresWorkspacesStore()
                ws = await ws_store.get_workspace(workspace_id)
                storage_base = getattr(ws, "storage_base_path", None) if ws else None
                artifacts_dir = getattr(ws, "artifacts_dir", None) or "artifacts"

                landing = TaskResultLandingService()
                landing.land_result(
                    workspace_id=workspace_id,
                    execution_id=body.execution_id,
                    result_data=result_data,
                    storage_base_path=storage_base,
                    artifacts_dirname=artifacts_dir,
                    thread_id=ctx.get("thread_id"),
                    project_id=ctx.get("project_id"),
                    task_id=ctx.get("task_id"),
                )
                logger.info(
                    "[AgentWS] Result landed for %s (storage=%s)",
                    body.execution_id,
                    storage_base or "DB-only",
                )
        except Exception:
            logger.exception(
                "[AgentWS] Result landing failed for %s (non-blocking)",
                body.execution_id,
            )

    return AgentResultResponse(
        accepted=True,
        execution_id=body.execution_id,
        message="Result accepted",
    )


@router.get("/api/v1/mcp/agent/result/{execution_id}")
async def get_agent_result(execution_id: str):
    """
    Retrieve a landed task result by execution_id.

    Returns status, storage_ref, summary, result_json, and attachments index.
    """
    try:
        from app.services.task_result_landing import TaskResultLandingService

        landing = TaskResultLandingService()
        result = landing.get_landed_result(execution_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"No result found for execution_id={execution_id}",
            )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_agent_result failed for %s", execution_id)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/api/v1/mcp/agent/status")
async def get_dispatch_status():
    """Get current dispatch manager status (diagnostic endpoint)."""
    manager = get_agent_dispatch_manager()
    return manager.get_status()


# ============================================================
#  Ack / Progress / Inflight endpoints
# ============================================================


class AckRequest(BaseModel):
    execution_id: str
    lease_id: str
    client_id: Optional[str] = None


class ProgressRequest(BaseModel):
    execution_id: str
    lease_id: str
    progress_pct: Optional[float] = None
    message: Optional[str] = None
    client_id: Optional[str] = None


@router.post("/api/v1/mcp/agent/ack")
async def ack_task_endpoint(body: AckRequest):
    """Acknowledge task pickup and extend lease (30s -> 300s)."""
    manager = get_agent_dispatch_manager()
    result = manager.ack_task(
        execution_id=body.execution_id,
        lease_id=body.lease_id,
        client_id=body.client_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reserved task or lease_id mismatch for {body.execution_id}",
        )
    return result


@router.post("/api/v1/mcp/agent/progress")
async def report_progress_endpoint(body: ProgressRequest):
    """Report task progress and reset lease timer."""
    manager = get_agent_dispatch_manager()
    result = manager.report_progress(
        execution_id=body.execution_id,
        lease_id=body.lease_id,
        progress_pct=body.progress_pct,
        message=body.message,
        client_id=body.client_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reserved task or lease_id mismatch for {body.execution_id}",
        )
    return result


@router.get("/api/v1/mcp/agent/inflight")
async def list_inflight_endpoint(
    client_id: str = Query(..., description="Client ID to list inflight tasks for"),
):
    """List reserved/inflight tasks for crash recovery."""
    manager = get_agent_dispatch_manager()
    tasks = manager.list_inflight(client_id=client_id)
    return {"tasks": tasks, "count": len(tasks)}
