from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from . import connection_manager as _connection_manager

logger = logging.getLogger("backend.app.routes.agent_dispatch.connection_manager")


class ConnectionDbRegistryMixin:
    @staticmethod
    def ensure_cross_worker_tables() -> None:
        """Create ws_connections and pending_dispatch tables if not exist."""
        conn = _connection_manager._get_core_db_connection(ensure_schema=False)
        if not conn:
            logger.warning(
                "[AgentWS] Cannot create cross-worker tables: " "no core DB connection"
            )
            return
        try:
            _connection_manager._ensure_cross_worker_tables(conn)
            conn.commit()
            _connection_manager._tables_ensured = True
            logger.info("[AgentWS] Cross-worker tables ensured")
        except Exception:
            conn.rollback()
            logger.exception("[AgentWS] Failed to create cross-worker tables")
        finally:
            conn.close()

    @staticmethod
    def _cleanup_stale_connections() -> None:
        """Remove ws_connections rows from dead workers on startup."""
        conn = _connection_manager._get_core_db_connection()
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
        conn = _connection_manager._get_core_db_connection()
        if not conn:
            return
        worker_instance_id = _connection_manager._get_worker_instance_id()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ws_connections "
                    "("
                    "workspace_id, client_id, worker_pid, worker_instance_id, "
                    "surface_type, authenticated"
                    ") "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (client_id) DO UPDATE SET "
                    "workspace_id = EXCLUDED.workspace_id, "
                    "worker_pid = EXCLUDED.worker_pid, "
                    "worker_instance_id = EXCLUDED.worker_instance_id, "
                    "surface_type = EXCLUDED.surface_type, "
                    "authenticated = EXCLUDED.authenticated, "
                    "connected_at = NOW(), "
                    "last_heartbeat = NOW()",
                    (
                        workspace_id,
                        client_id,
                        os.getpid(),
                        worker_instance_id,
                        surface_type,
                        authenticated,
                    ),
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
        conn = _connection_manager._get_core_db_connection()
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
    def _db_has_connections(
        workspace_id: Optional[str] = None,
        surface_type: Optional[str] = None,
    ) -> bool:
        """Query PostgreSQL for live WS connections."""
        conn = _connection_manager._get_core_db_connection()
        if not conn:
            raise RuntimeError("No core DB connection")
        try:
            with conn.cursor() as cur:
                if workspace_id and surface_type:
                    cur.execute(
                        "SELECT COUNT(*) FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND surface_type = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds'",
                        (workspace_id, surface_type),
                    )
                elif workspace_id:
                    cur.execute(
                        "SELECT COUNT(*) FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds'",
                        (workspace_id,),
                    )
                elif surface_type:
                    cur.execute(
                        "SELECT COUNT(*) FROM ws_connections "
                        "WHERE surface_type = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds'",
                        (surface_type,),
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
        conn = _connection_manager._get_core_db_connection()
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
    def _db_update_pending_progress(execution_id: str) -> None:
        """Update progress timestamp in pending_dispatch for cross-worker visibility."""
        conn = _connection_manager._get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pending_dispatch SET last_progress_at = NOW() "
                    "WHERE execution_id = %s",
                    (execution_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    @staticmethod
    def _db_mark_authenticated(client_id: str) -> None:
        """Mark a WS connection as authenticated in PostgreSQL."""
        conn = _connection_manager._get_core_db_connection()
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

    @staticmethod
    def _db_get_dispatch_target(
        workspace_id: str,
        client_id: Optional[str] = None,
        surface_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the freshest authenticated connection for a workspace."""
        conn = _connection_manager._get_core_db_connection()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                if client_id and surface_type:
                    cur.execute(
                        "SELECT client_id, worker_pid, worker_instance_id, "
                        "surface_type "
                        "FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND client_id = %s "
                        "AND surface_type = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds' "
                        "ORDER BY last_heartbeat DESC "
                        "LIMIT 1",
                        (workspace_id, client_id, surface_type),
                    )
                elif client_id:
                    cur.execute(
                        "SELECT client_id, worker_pid, worker_instance_id, "
                        "surface_type "
                        "FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND client_id = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds' "
                        "ORDER BY last_heartbeat DESC "
                        "LIMIT 1",
                        (workspace_id, client_id),
                    )
                elif surface_type:
                    cur.execute(
                        "SELECT client_id, worker_pid, worker_instance_id, "
                        "surface_type "
                        "FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND surface_type = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds' "
                        "ORDER BY last_heartbeat DESC "
                        "LIMIT 1",
                        (workspace_id, surface_type),
                    )
                else:
                    cur.execute(
                        "SELECT client_id, worker_pid, worker_instance_id, "
                        "surface_type "
                        "FROM ws_connections "
                        "WHERE workspace_id = %s "
                        "AND authenticated = TRUE "
                        "AND last_heartbeat > NOW() - INTERVAL '90 seconds' "
                        "ORDER BY last_heartbeat DESC "
                        "LIMIT 1",
                        (workspace_id,),
                    )
                row = cur.fetchone()
                if not row:
                    return None
                remote_client_id, worker_pid, worker_instance_id, surface_type = row
                return {
                    "workspace_id": workspace_id,
                    "client_id": remote_client_id,
                    "worker_pid": worker_pid,
                    "worker_instance_id": worker_instance_id,
                    "surface_type": surface_type,
                }
        finally:
            conn.close()
