"""
Agent Dispatch Manager — Composed class with mixin architecture.

The AgentDispatchManager composes five focused mixins:
  - ConnectionMixin: client connect/disconnect/lookup
  - BridgeControlMixin: bridge control channel
  - AuthMixin: token + HMAC nonce authentication
  - TaskDispatchMixin: task dispatch + WS message handling
  - LeaseManagerMixin: REST polling lease management
"""

import asyncio
import logging
import os
from collections import OrderedDict, defaultdict
from typing import Any, Dict, List, Optional

from .models import (
    AgentClient,
    AgentControlClient,
    InflightTask,
    PendingTask,
    ReservedTask,
)
from .connection_manager import ConnectionMixin
from .bridge_control import BridgeControlMixin
from .auth import AuthMixin
from .task_dispatcher import TaskDispatchMixin
from .lease_manager import LeaseManagerMixin

logger = logging.getLogger(__name__)


class AgentDispatchManager(
    ConnectionMixin,
    BridgeControlMixin,
    AuthMixin,
    TaskDispatchMixin,
    LeaseManagerMixin,
):
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

        # bridge_id -> AgentControlClient (control channel)
        self._bridge_controls: Dict[str, AgentControlClient] = {}

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
