"""
Agent Dispatch -- Cross-worker dispatch mixin.

Handles DB-mediated task dispatch between Uvicorn workers,
pending dispatch consumer loop, and all DB helper methods.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .models import InflightTask
from .connection_manager import _get_core_db_connection

logger = logging.getLogger(__name__)


class CrossWorkerMixin:
    """Mixin: cross-worker dispatch via PostgreSQL pending_dispatch table."""

    async def _cross_worker_dispatch(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """Dispatch a task via PostgreSQL for a remote worker to pick up.

        Flow:
          1. INSERT into pending_dispatch (status='pending')
          2. Poll pending_dispatch.result_data for completed result
          3. Return result or timeout error
        """
        # Write task to pending_dispatch
        try:
            await asyncio.to_thread(
                self._db_insert_pending_dispatch,
                execution_id,
                workspace_id,
                message,
            )
        except Exception as e:
            logger.exception(
                f"[AgentWS] Failed to insert pending_dispatch " f"for {execution_id}"
            )
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": f"Cross-worker dispatch failed: {e}",
            }

        # Poll pending_dispatch for result written by consumer worker.
        # Activity-aware: check last_progress_at to avoid killing active tasks.
        poll_interval = 0.5
        last_activity = time.monotonic()
        last_known_progress_at = None

        while True:
            try:
                result, status, progress_at = await asyncio.to_thread(
                    self._db_poll_pending_result, execution_id
                )
                if result is not None:
                    logger.info(
                        f"[AgentWS] Cross-worker result received " f"for {execution_id}"
                    )
                    return result

                # Check for progress activity
                if progress_at and progress_at != last_known_progress_at:
                    last_activity = time.monotonic()
                    last_known_progress_at = progress_at
            except Exception:
                pass

            idle = time.monotonic() - last_activity
            if idle > timeout:
                break
            await asyncio.sleep(poll_interval)

        # Timeout — no activity
        try:
            await asyncio.to_thread(
                self._db_update_pending_status, execution_id, "timeout"
            )
        except Exception:
            pass

        logger.error(
            f"[AgentWS] Cross-worker dispatch: no activity for "
            f"{timeout}s, exec={execution_id}"
        )
        return {
            "execution_id": execution_id,
            "status": "timeout",
            "error": f"No activity for {timeout:.0f}s (cross-worker)",
        }

    async def consume_pending_dispatches(self) -> None:
        """Background task: poll pending_dispatch and dispatch locally.

        Run this only on workers that have local WS connections.
        Picks pending tasks, dispatches them via local WS, awaits
        the result future, and writes result back to pending_dispatch.
        """
        logger.info(
            f"[AgentWS] Starting pending dispatch consumer "
            f"(worker pid={os.getpid()})"
        )
        # Track consecutive no-client cycles for backoff
        no_client_backoff = 0
        MAX_NO_CLIENT_BACKOFF = 30  # max 30s between retries
        while True:
            try:
                # Only consume if this worker has local WS connections
                if not self.has_local_connections():
                    await asyncio.sleep(1.0)
                    continue

                rows = await asyncio.to_thread(
                    self._db_pick_pending_dispatches, limit=5
                )
                if not rows:
                    no_client_backoff = 0  # Reset on empty queue
                    await asyncio.sleep(0.5)
                    continue

                had_no_client = False
                for row in rows:
                    exec_id = row["execution_id"]
                    ws_id = row["workspace_id"]
                    payload = row["payload"]

                    logger.info(
                        f"[AgentWS] Consumer picked cross-worker task "
                        f"{exec_id} for workspace {ws_id}"
                    )

                    # Dispatch via local WS (get_client will find local)
                    client = self.get_client(ws_id)
                    if not client:
                        had_no_client = True
                        logger.warning(
                            f"[AgentWS] No local client for {ws_id}, "
                            f"marking task {exec_id} as no_client"
                        )
                        # Mark as 'no_client' so it is NOT re-picked
                        # immediately. A future flush_pending or client
                        # reconnect will handle it.
                        await asyncio.to_thread(
                            self._db_update_pending_status,
                            exec_id,
                            "no_client",
                        )
                        continue

                    # Reset backoff on successful client match
                    no_client_backoff = 0

                    # Create inflight entry for this task
                    loop = asyncio.get_event_loop()
                    result_future: asyncio.Future = loop.create_future()
                    inflight = InflightTask(
                        execution_id=exec_id,
                        workspace_id=ws_id,
                        client_id=client.client_id,
                        result_future=result_future,
                        payload=payload,
                    )
                    self._inflight[exec_id] = inflight

                    try:
                        await client.websocket.send_text(json.dumps(payload))
                        logger.info(
                            f"[AgentWS] Consumer dispatched {exec_id} to "
                            f"client {client.client_id}"
                        )
                    except Exception as e:
                        self._inflight.pop(exec_id, None)
                        logger.error(
                            f"[AgentWS] Consumer failed to send " f"{exec_id}: {e}"
                        )
                        # Write failure result to pending_dispatch
                        fail_result = {
                            "execution_id": exec_id,
                            "status": "failed",
                            "error": f"Consumer dispatch failed: {e}",
                        }
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            fail_result,
                        )
                        continue

                    # Await the result with activity-aware timeout
                    consumer_timeout = 600.0
                    consumer_last_activity = time.monotonic()
                    consumer_result = None

                    while True:
                        try:
                            consumer_result = await asyncio.wait_for(
                                asyncio.shield(result_future),
                                timeout=30.0,
                            )
                            break
                        except asyncio.TimeoutError:
                            inflight_check = self._inflight.get(exec_id)
                            if (
                                inflight_check
                                and inflight_check.last_progress_at
                                > consumer_last_activity
                            ):
                                consumer_last_activity = inflight_check.last_progress_at

                            idle_time = time.monotonic() - consumer_last_activity
                            if idle_time > consumer_timeout:
                                break

                    if consumer_result is not None:
                        logger.info(
                            f"[AgentWS] Consumer got result for "
                            f"{exec_id}: status="
                            f"{consumer_result.get('status')}"
                        )
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            consumer_result,
                        )
                    else:
                        self._inflight.pop(exec_id, None)
                        logger.error(
                            f"[AgentWS] Consumer: no activity for "
                            f"{consumer_timeout}s on {exec_id}"
                        )
                        timeout_result = {
                            "execution_id": exec_id,
                            "status": "timeout",
                            "error": f"Consumer-side: no activity "
                            f"for {consumer_timeout:.0f}s",
                        }
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            timeout_result,
                        )

                # Exponential backoff when all rows had no client
                if had_no_client:
                    no_client_backoff = min(
                        no_client_backoff + 2, MAX_NO_CLIENT_BACKOFF
                    )
                    logger.info(
                        f"[AgentWS] No-client backoff: sleeping "
                        f"{no_client_backoff}s"
                    )
                    await asyncio.sleep(no_client_backoff)

            except Exception:
                logger.exception("[AgentWS] Error in pending dispatch consumer")
                await asyncio.sleep(2.0)

    # ============================================================
    #  DB helpers for cross-worker dispatch
    # ============================================================

    @staticmethod
    def _db_insert_pending_dispatch(
        execution_id: str,
        workspace_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """Insert a task into pending_dispatch table."""
        conn = _get_core_db_connection()
        if not conn:
            raise RuntimeError("No core DB connection")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pending_dispatch "
                    "(execution_id, workspace_id, payload, status) "
                    "VALUES (%s, %s, %s, 'pending') "
                    "ON CONFLICT (execution_id) DO NOTHING",
                    (execution_id, workspace_id, json.dumps(payload)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _db_poll_pending_result(
        execution_id: str,
    ):
        """Poll pending_dispatch for result and progress activity.

        Returns:
            Tuple of (result_data_or_None, status, last_progress_at)
        """
        conn = _get_core_db_connection()
        if not conn:
            return None, None, None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT result_data, status, last_progress_at "
                    "FROM pending_dispatch "
                    "WHERE execution_id = %s",
                    (execution_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None, None, None
                result_data, status, progress_at = row
                if status == "done" and result_data is not None:
                    if isinstance(result_data, str):
                        return json.loads(result_data), status, progress_at
                    return result_data, status, progress_at
                return None, status, progress_at
        finally:
            conn.close()

    @staticmethod
    def _db_write_pending_result(
        execution_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Write result_data to pending_dispatch for cross-worker retrieval."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pending_dispatch "
                    "SET result_data = %s, status = 'done', "
                    "completed_at = NOW() "
                    "WHERE execution_id = %s",
                    (json.dumps(result), execution_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                f"[AgentWS] Failed to write result to "
                f"pending_dispatch for {execution_id}"
            )
        finally:
            conn.close()

    @staticmethod
    def _db_update_pending_status(execution_id: str, status: str) -> None:
        """Update pending_dispatch status."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pending_dispatch SET status = %s "
                    "WHERE execution_id = %s",
                    (status, execution_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    @staticmethod
    def _db_pick_pending_dispatches(limit: int = 5) -> List[Dict[str, Any]]:
        """Pick pending tasks atomically using FOR UPDATE SKIP LOCKED."""
        conn = _get_core_db_connection()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, execution_id, workspace_id, payload "
                    "FROM pending_dispatch "
                    "WHERE status = 'pending' "
                    "ORDER BY created_at ASC "
                    "LIMIT %s "
                    "FOR UPDATE SKIP LOCKED",
                    (limit,),
                )
                rows = cur.fetchall()
                if not rows:
                    conn.rollback()
                    return []

                result = []
                for row in rows:
                    row_id, exec_id, ws_id, payload_data = row
                    cur.execute(
                        "UPDATE pending_dispatch "
                        "SET status = 'picked', picked_by_pid = %s, "
                        "picked_at = NOW() "
                        "WHERE id = %s",
                        (os.getpid(), row_id),
                    )
                    # Parse payload
                    if isinstance(payload_data, str):
                        payload_data = json.loads(payload_data)
                    result.append(
                        {
                            "execution_id": exec_id,
                            "workspace_id": ws_id,
                            "payload": payload_data,
                        }
                    )

                conn.commit()
                return result
        except Exception:
            conn.rollback()
            return []
        finally:
            conn.close()
