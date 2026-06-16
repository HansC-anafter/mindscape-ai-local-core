from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from .models import AgentClient, PendingTask

logger = logging.getLogger("backend.app.routes.agent_dispatch.connection_manager")


class ConnectionLifecycleMixin:
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

        # Pre-connect cleanup: if same client_id already exists (reconnect),
        # call disconnect() first to re-queue any inflight tasks.
        # Without this, _clients[ws_id][cid] is silently overwritten and
        # the old connection's inflight Futures are orphaned forever.
        existing = self._clients.get(workspace_id, {}).get(cid)
        if existing:
            logger.warning(
                f"[AgentWS] Client {cid} reconnecting to {workspace_id}, "
                f"cleaning up old connection (re-queue inflight tasks)"
            )
            self.disconnect(existing)

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

    def disconnect(
        self,
        client: AgentClient,
        *,
        requeue_inflight: bool = True,
    ) -> None:
        """Remove a client connection and optionally re-queue inflight tasks."""
        ws_id = client.workspace_id
        cid = client.client_id

        if ws_id in self._clients:
            self._clients[ws_id].pop(cid, None)
            if not self._clients[ws_id]:
                del self._clients[ws_id]

        # Remove from PostgreSQL cross-worker registry
        self._db_unregister_connection(cid)

        if not requeue_inflight:
            logger.info(
                "[AgentWS] Client %s evicted from workspace %s without re-queue",
                cid,
                ws_id,
            )
            return

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

            # If another worker is awaiting the result, hand retry control
            # back to the origin worker instead of trapping it in a local queue.
            if task.origin_worker_id and task.origin_worker_id != self._ensure_worker_identity():
                self._inflight.pop(eid)
                try:
                    self._db_release_pending_dispatch(eid, "pending")
                except Exception:
                    logger.exception(
                        "[AgentWS] Failed to release durable dispatch row for %s",
                        eid,
                    )
                if task.payload:
                    try:
                        asyncio.create_task(
                            self._relay_to_origin_worker(
                                task,
                                "dispatch_failed",
                                client_id=cid,
                                error=(
                                    f"Client {cid} disconnected while executing {eid}"
                                ),
                                retry_transport="db_polling",
                            )
                        )
                    except Exception:
                        logger.exception(
                            "[AgentWS] Failed to notify origin worker about disconnect "
                            "for %s",
                            eid,
                        )
                logger.warning(
                    "[AgentWS] Remote-origin task %s lost client %s; "
                    "origin worker will retry via shared transport",
                    eid,
                    cid,
                )
                continue

            # Re-queue with payload if available.
            # KEEP the inflight entry alive (set client_id='pending')
            # so flush_pending can reconnect the original result_future.
            if task.payload:
                task.client_id = "pending"  # mark as awaiting re-dispatch
                try:
                    self._db_release_pending_dispatch(eid, "pending")
                except Exception:
                    logger.exception(
                        "[AgentWS] Failed to release durable dispatch row for %s",
                        eid,
                    )
                pending = PendingTask(
                    execution_id=eid,
                    workspace_id=ws_id,
                    payload=task.payload,
                    attempts=1,
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
