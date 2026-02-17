"""
Agent Dispatch — Connection lifecycle mixin.

Handles WebSocket client accept, disconnect, heartbeat tracking,
and client lookup by workspace/client ID.

Cross-worker support:
  Registers connections in PostgreSQL (ws_connections table) so that
  all uvicorn workers can discover live WS connections regardless of
  which worker accepted the socket.
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from .models import AgentClient, InflightTask, PendingTask

logger = logging.getLogger(__name__)

_CREATE_WS_CONNECTIONS_SQL = """
CREATE TABLE IF NOT EXISTS ws_connections (
    id SERIAL PRIMARY KEY,
    workspace_id VARCHAR(64) NOT NULL,
    client_id VARCHAR(64) NOT NULL UNIQUE,
    worker_pid INTEGER NOT NULL,
    surface_type VARCHAR(32) DEFAULT 'gemini_cli',
    authenticated BOOLEAN DEFAULT FALSE,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ws_conn_workspace
    ON ws_connections(workspace_id);
"""

_CREATE_PENDING_DISPATCH_SQL = """
CREATE TABLE IF NOT EXISTS pending_dispatch (
    id SERIAL PRIMARY KEY,
    execution_id VARCHAR(64) UNIQUE NOT NULL,
    workspace_id VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) DEFAULT 'pending',
    result_data JSONB,
    picked_by_pid INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    picked_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_pending_dispatch_status
    ON pending_dispatch(status);
"""
_tables_ensured = False


def _get_core_db_connection():
    """Get a raw psycopg2 connection to the core database.

    On the first successful call, ensures cross-worker tables exist.
    """
    global _tables_ensured

    from backend.app.database.config import get_postgres_url_core

    url = get_postgres_url_core(required=False)
    if not url:
        return None
    import psycopg2

    conn = psycopg2.connect(url)

    if not _tables_ensured:
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_WS_CONNECTIONS_SQL)
                cur.execute(_CREATE_PENDING_DISPATCH_SQL)
            conn.commit()
            _tables_ensured = True
            logger.info("[AgentWS] Cross-worker tables ensured (on-demand)")
        except Exception:
            conn.rollback()
            logger.exception("[AgentWS] Failed to create cross-worker tables")

    return conn


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

        # Register in PostgreSQL for cross-worker visibility
        self._db_register_connection(
            workspace_id=workspace_id,
            client_id=cid,
            surface_type=surface_type,
            authenticated=client.authenticated,
        )

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

        # Remove from PostgreSQL cross-worker registry
        self._db_unregister_connection(cid)

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
        """Check if there are any authenticated connections (cross-worker).

        Queries the PostgreSQL ws_connections table so that ALL uvicorn
        workers return a consistent answer. Falls back to in-memory
        check if the DB query fails.
        """
        try:
            return self._db_has_connections(workspace_id)
        except Exception:
            # Fallback to local in-memory check on DB failure
            if workspace_id:
                clients = self._clients.get(workspace_id, {})
                return any(c.authenticated for c in clients.values())
            return any(
                c.authenticated
                for ws_clients in self._clients.values()
                for c in ws_clients.values()
            )

    def has_local_connections(self, workspace_id: Optional[str] = None) -> bool:
        """Check in-memory only (current worker). Used for local dispatch."""
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

        Only returns clients from this worker's in-memory store.
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
    #  PostgreSQL cross-worker helpers
    # ============================================================

    @staticmethod
    def ensure_cross_worker_tables() -> None:
        """Create ws_connections and pending_dispatch tables if not exist."""
        conn = _get_core_db_connection()
        if not conn:
            logger.warning(
                "[AgentWS] Cannot create cross-worker tables: " "no core DB connection"
            )
            return
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_WS_CONNECTIONS_SQL)
                cur.execute(_CREATE_PENDING_DISPATCH_SQL)
            conn.commit()
            logger.info("[AgentWS] Cross-worker tables ensured")
        except Exception:
            conn.rollback()
            logger.exception("[AgentWS] Failed to create cross-worker tables")
        finally:
            conn.close()

    @staticmethod
    def _cleanup_stale_connections() -> None:
        """Remove ws_connections rows from dead workers on startup."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ws_connections WHERE "
                    "last_heartbeat < NOW() - INTERVAL '90 seconds'"
                )
                deleted = cur.rowcount
            conn.commit()
            if deleted:
                logger.info(f"[AgentWS] Cleaned up {deleted} stale ws_connections rows")
        except Exception:
            conn.rollback()
            logger.exception("[AgentWS] Failed to cleanup stale ws_connections")
        finally:
            conn.close()

    def _db_register_connection(
        self,
        workspace_id: str,
        client_id: str,
        surface_type: str,
        authenticated: bool,
    ) -> None:
        """Register this WS connection in PostgreSQL."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ws_connections "
                    "(workspace_id, client_id, worker_pid, surface_type, authenticated) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (client_id) DO UPDATE SET "
                    "workspace_id = EXCLUDED.workspace_id, "
                    "worker_pid = EXCLUDED.worker_pid, "
                    "surface_type = EXCLUDED.surface_type, "
                    "authenticated = EXCLUDED.authenticated, "
                    "connected_at = NOW(), "
                    "last_heartbeat = NOW()",
                    (workspace_id, client_id, os.getpid(), surface_type, authenticated),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                f"[AgentWS] Failed to register ws_connection for {client_id}"
            )
        finally:
            conn.close()

    @staticmethod
    def _db_unregister_connection(client_id: str) -> None:
        """Remove this WS connection from PostgreSQL."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ws_connections WHERE client_id = %s",
                    (client_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                f"[AgentWS] Failed to unregister ws_connection for {client_id}"
            )
        finally:
            conn.close()

    @staticmethod
    def _db_has_connections(workspace_id: Optional[str] = None) -> bool:
        """Query PostgreSQL for live WS connections."""
        conn = _get_core_db_connection()
        if not conn:
            raise RuntimeError("No core DB connection")
        try:
            with conn.cursor() as cur:
                if workspace_id:
                    cur.execute(
                        "SELECT COUNT(*) FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds'",
                        (workspace_id,),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM ws_connections "
                        "WHERE authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds'"
                    )
                row = cur.fetchone()
                return bool(row and row[0] > 0)
        finally:
            conn.close()

    @staticmethod
    def _db_update_heartbeat(client_id: str) -> None:
        """Update heartbeat timestamp in PostgreSQL."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ws_connections SET last_heartbeat = NOW() "
                    "WHERE client_id = %s",
                    (client_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    @staticmethod
    def _db_mark_authenticated(client_id: str) -> None:
        """Mark a WS connection as authenticated in PostgreSQL."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ws_connections SET authenticated = TRUE "
                    "WHERE client_id = %s",
                    (client_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
