"""
Agent Dispatch -- DB fallback transport.

PostgreSQL-based cross-worker dispatch: pending_dispatch table CRUD,
DB polling dispatcher, and background consumer.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List

from .connection_manager import _get_core_db_connection
from .models import InflightTask

logger = logging.getLogger(__name__)


class DbFallbackMixin:
    """Mixin: PostgreSQL pending_dispatch cross-worker transport."""

    async def _cross_worker_dispatch_via_db(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """Dispatch a task via PostgreSQL for a remote worker to pick up."""
        try:
            await asyncio.to_thread(
                self._db_insert_pending_dispatch,
                execution_id,
                workspace_id,
                message,
            )
        except Exception as exc:
            logger.exception(
                "[AgentWS] Failed to insert pending_dispatch for %s",
                execution_id,
            )
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": f"Cross-worker DB fallback failed: {exc}",
            }

        poll_interval = 0.5
        last_activity = time.monotonic()
        last_known_progress_at = None

        while True:
            try:
                result, _, progress_at = await asyncio.to_thread(
                    self._db_poll_pending_result,
                    execution_id,
                )
                if result is not None:
                    logger.info(
                        "[AgentWS] DB fallback result received for %s",
                        execution_id,
                    )
                    return result

                if progress_at and progress_at != last_known_progress_at:
                    last_activity = time.monotonic()
                    last_known_progress_at = progress_at
            except Exception:
                pass

            idle = time.monotonic() - last_activity
            if idle > timeout:
                break
            await asyncio.sleep(poll_interval)

        try:
            await asyncio.to_thread(
                self._db_update_pending_status,
                execution_id,
                "timeout",
            )
        except Exception:
            pass

        logger.error(
            "[AgentWS] DB fallback cross-worker dispatch timed out after %.0fs "
            "(exec=%s)",
            timeout,
            execution_id,
        )
        return {
            "execution_id": execution_id,
            "status": "timeout",
            "error": f"No activity for {timeout:.0f}s (cross-worker)",
        }

    async def consume_pending_dispatches(self) -> None:
        """Background task: poll pending_dispatch and dispatch locally."""
        logger.info(
            "[AgentWS] Starting pending dispatch consumer (worker=%s)",
            self._ensure_worker_identity(),
        )
        no_client_backoff = 0
        max_no_client_backoff = 30

        while True:
            try:
                if not self.has_local_connections():
                    await asyncio.sleep(1.0)
                    continue

                rows = await asyncio.to_thread(
                    self._db_pick_pending_dispatches, limit=5
                )
                if not rows:
                    no_client_backoff = 0
                    await asyncio.sleep(0.5)
                    continue

                had_no_client = False
                for row in rows:
                    exec_id = row["execution_id"]
                    ws_id = row["workspace_id"]
                    payload = row["payload"]

                    logger.info(
                        "[AgentWS] Consumer picked DB fallback task %s "
                        "for workspace %s",
                        exec_id,
                        ws_id,
                    )

                    client = self.get_client(ws_id)
                    if not client:
                        had_no_client = True
                        logger.warning(
                            "[AgentWS] No local client for %s, marking task %s as no_client",
                            ws_id,
                            exec_id,
                        )
                        await asyncio.to_thread(
                            self._db_update_pending_status,
                            exec_id,
                            "no_client",
                        )
                        continue

                    no_client_backoff = 0

                    loop = asyncio.get_event_loop()
                    result_future: asyncio.Future = loop.create_future()
                    inflight = InflightTask(
                        execution_id=exec_id,
                        workspace_id=ws_id,
                        client_id=client.client_id,
                        result_future=result_future,
                        payload=payload,
                        thread_id=(payload.get("context") or {}).get("thread_id"),
                        project_id=(payload.get("context") or {}).get("project_id"),
                    )
                    self._inflight[exec_id] = inflight

                    try:
                        await client.websocket.send_text(json.dumps(payload))
                        logger.info(
                            "[AgentWS] Consumer dispatched %s to client %s",
                            exec_id,
                            client.client_id,
                        )
                    except Exception as exc:
                        self._inflight.pop(exec_id, None)
                        logger.error(
                            "[AgentWS] Consumer failed to send %s: %s",
                            exec_id,
                            exc,
                        )
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            {
                                "execution_id": exec_id,
                                "status": "failed",
                                "error": f"Consumer dispatch failed: {exc}",
                            },
                        )
                        continue

                    consumer_result = await self._await_inflight_result(
                        exec_id,
                        result_future,
                        600.0,
                        context_label="db-consumer",
                    )

                    if consumer_result.get("status") != "timeout":
                        logger.info(
                            "[AgentWS] Consumer got result for %s: status=%s",
                            exec_id,
                            consumer_result.get("status"),
                        )
                    await asyncio.to_thread(
                        self._db_write_pending_result,
                        exec_id,
                        consumer_result,
                    )

                if had_no_client:
                    no_client_backoff = min(
                        no_client_backoff + 2,
                        max_no_client_backoff,
                    )
                    logger.info(
                        "[AgentWS] No-client backoff: sleeping %ss",
                        no_client_backoff,
                    )
                    await asyncio.sleep(no_client_backoff)

            except asyncio.CancelledError:
                raise
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
    def _db_poll_pending_result(execution_id: str):
        """Poll pending_dispatch for result and progress activity."""
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
                "[AgentWS] Failed to write result to pending_dispatch for %s",
                execution_id,
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
                    "WHERE status IN ('pending', 'no_client') "
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
