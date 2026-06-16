"""
Agent Dispatch — Connection lifecycle mixin.

Handles WebSocket client accept, disconnect, heartbeat tracking,
and client lookup by workspace/client ID.

Cross-worker support:
  Registers connections in PostgreSQL (ws_connections table) so that
  all uvicorn workers can discover live WS connections regardless of
  which worker accepted the socket.
"""

import asyncio
import logging
import os
import socket
import time
import uuid
from typing import Any, Dict, List, Optional

from .models import AgentClient, InflightTask, PendingTask

logger = logging.getLogger(__name__)

_CREATE_WS_CONNECTIONS_SQL = """
CREATE TABLE IF NOT EXISTS ws_connections (
    id SERIAL PRIMARY KEY,
    workspace_id VARCHAR(64) NOT NULL,
    client_id TEXT NOT NULL UNIQUE,
    worker_pid INTEGER NOT NULL,
    worker_instance_id VARCHAR(128),
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
    picked_by_worker_instance_id VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    picked_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_progress_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_pending_dispatch_status
    ON pending_dispatch(status);
"""
_tables_ensured = False
_CROSS_WORKER_SCHEMA_LOCK_NAMESPACE = 487629357
_CROSS_WORKER_SCHEMA_LOCK_KEY = 20260505


def _get_worker_instance_id() -> str:
    """Return a worker identity stable for this process lifetime."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _ensure_cross_worker_tables(conn) -> None:
    """Create/migrate cross-worker dispatch tables under one schema DDL lock."""
    with conn.cursor() as cur:
        # Serialize only schema DDL across workers; normal dispatch traffic is unaffected.
        cur.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            (_CROSS_WORKER_SCHEMA_LOCK_NAMESPACE, _CROSS_WORKER_SCHEMA_LOCK_KEY),
        )
        cur.execute(_CREATE_WS_CONNECTIONS_SQL)
        cur.execute(_CREATE_PENDING_DISPATCH_SQL)
        cur.execute(
            "ALTER TABLE ws_connections "
            "ADD COLUMN IF NOT EXISTS worker_instance_id "
            "VARCHAR(128)"
        )
        cur.execute("ALTER TABLE ws_connections ALTER COLUMN client_id TYPE TEXT")
        cur.execute(
            "ALTER TABLE pending_dispatch "
            "ADD COLUMN IF NOT EXISTS last_progress_at "
            "TIMESTAMP WITH TIME ZONE"
        )
        cur.execute(
            "ALTER TABLE pending_dispatch "
            "ADD COLUMN IF NOT EXISTS picked_by_worker_instance_id "
            "VARCHAR(128)"
        )


def _get_core_db_connection(ensure_schema: bool = True):
    """Get a raw DB-API connection from the SQLAlchemy engine pool.

    Uses the centralized engine_postgres_core pool (pool_size=5,
    max_overflow=10, pool_recycle=1800) instead of creating ephemeral
    psycopg2 connections that bypass pool management.

    On the first successful call, ensures cross-worker tables exist.
    """
    global _tables_ensured

    if ensure_schema and not _tables_ensured:
        schema_conn = None
        try:
            from app.database.config import get_postgres_url_core_session
            from app.database.engine_factory import create_session_semantics_engine

            schema_engine = create_session_semantics_engine(
                get_postgres_url_core_session(),
                "local-core-agent-dispatch-schema",
            )
            schema_conn = schema_engine.raw_connection()
            _ensure_cross_worker_tables(schema_conn)
            schema_conn.commit()
            _tables_ensured = True
            logger.info("[AgentWS] Cross-worker tables ensured (on-demand)")
        except Exception:
            if schema_conn is not None:
                schema_conn.rollback()
            logger.exception("[AgentWS] Failed to create cross-worker tables")
        finally:
            if schema_conn is not None:
                schema_conn.close()
            if "schema_engine" in locals():
                schema_engine.dispose()

    try:
        from app.database.engine import engine_postgres_core

        if engine_postgres_core is None:
            return None
        conn = engine_postgres_core.raw_connection()
    except Exception:
        logger.warning("[AgentWS] Failed to get pooled DB connection")
        return None

    return conn

from .connection_db_registry import ConnectionDbRegistryMixin
from .connection_lifecycle import ConnectionLifecycleMixin
from .connection_lookup import ConnectionLookupMixin


class ConnectionMixin(
    ConnectionLifecycleMixin,
    ConnectionLookupMixin,
    ConnectionDbRegistryMixin,
):
    """Mixin: IDE agent connection lifecycle management."""


__all__ = [
    "ConnectionMixin",
    "_CREATE_WS_CONNECTIONS_SQL",
    "_CREATE_PENDING_DISPATCH_SQL",
    "_CROSS_WORKER_SCHEMA_LOCK_NAMESPACE",
    "_CROSS_WORKER_SCHEMA_LOCK_KEY",
    "_tables_ensured",
    "_get_worker_instance_id",
    "_ensure_cross_worker_tables",
    "_get_core_db_connection",
]
