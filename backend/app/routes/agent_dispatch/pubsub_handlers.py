"""
Agent Dispatch -- Pub/sub envelope handlers.

Routes inbound worker-to-worker messages and relays WS activity
(ack, progress, result) from the socket-owning worker back to the
origin worker.
"""

import json
import logging
import time
from typing import Any, Dict

from .models import InflightTask

logger = logging.getLogger(__name__)


class PubSubHandlersMixin:
    """Mixin: pub/sub envelope routing and event handlers."""

    async def _relay_to_origin_worker(
        self,
        inflight: InflightTask,
        event_type: str,
        **payload: Any,
    ) -> bool:
        """Relay WS activity from the socket-owning worker to the origin worker."""
        origin_worker_id = inflight.origin_worker_id
        if not origin_worker_id:
            return False
        if origin_worker_id == self._ensure_worker_identity():
            return False

        envelope = {
            "type": event_type,
            "execution_id": inflight.execution_id,
            "workspace_id": inflight.workspace_id,
            "origin_worker_id": origin_worker_id,
            **payload,
        }
        return await self._publish_pubsub_message(origin_worker_id, envelope)

    async def _handle_pubsub_envelope(self, envelope: Dict[str, Any]) -> None:
        """Route a worker-to-worker pub/sub envelope."""
        msg_type = envelope.get("type")

        if msg_type == "dispatch_request":
            await self._handle_pubsub_dispatch_request(envelope)
        elif msg_type == "dispatch_ack":
            self._handle_pubsub_dispatch_ack(envelope)
        elif msg_type == "dispatch_progress":
            self._handle_pubsub_dispatch_progress(envelope)
        elif msg_type == "dispatch_result":
            self._handle_pubsub_dispatch_result(envelope)
        elif msg_type == "dispatch_failed":
            self._handle_pubsub_dispatch_failed(envelope)
        else:
            logger.warning("[AgentWS] Unknown pub/sub envelope type: %s", msg_type)

    async def _handle_pubsub_dispatch_request(
        self,
        envelope: Dict[str, Any],
    ) -> None:
        """Dispatch a remote task to the local WS client owned by this worker."""
        execution_id = envelope.get("execution_id", "")
        workspace_id = envelope.get("workspace_id", "")
        target_client_id = envelope.get("client_id")
        origin_worker_id = envelope.get("origin_worker_id")
        payload = envelope.get("payload") or {}
        surface_type = payload.get("agent_id") or payload.get("surface_type")

        client = self.get_client(
            workspace_id,
            target_client_id,
            surface_type=surface_type,
        )
        if not client and not target_client_id:
            client = self.get_client(workspace_id, surface_type=surface_type)

        if not client:
            await self._publish_pubsub_message(
                origin_worker_id,
                {
                    "type": "dispatch_failed",
                    "execution_id": execution_id,
                    "error": (
                        f"Worker {self._ensure_worker_identity()} has no local client "
                        f"for workspace {workspace_id}"
                    ),
                    "retry_transport": "db_polling",
                },
            )
            return

        inflight = InflightTask(
            execution_id=execution_id,
            workspace_id=workspace_id,
            client_id=client.client_id,
            origin_worker_id=origin_worker_id,
            payload=payload,
            thread_id=(payload.get("context") or {}).get("thread_id"),
            project_id=(payload.get("context") or {}).get("project_id"),
        )
        self._inflight[execution_id] = inflight

        try:
            await client.websocket.send_text(json.dumps(payload))
            await self._publish_pubsub_message(
                origin_worker_id,
                {
                    "type": "dispatch_ack",
                    "execution_id": execution_id,
                    "client_id": client.client_id,
                },
            )
            logger.info(
                "[AgentWS] Pub/sub dispatched %s to local client %s " "(origin=%s)",
                execution_id,
                client.client_id,
                origin_worker_id,
            )
        except Exception as exc:
            self._inflight.pop(execution_id, None)
            logger.exception(
                "[AgentWS] Pub/sub send failed for %s via client %s",
                execution_id,
                client.client_id,
            )
            await self._publish_pubsub_message(
                origin_worker_id,
                {
                    "type": "dispatch_failed",
                    "execution_id": execution_id,
                    "error": f"Remote worker send failed: {exc}",
                    "retry_transport": "db_polling",
                },
            )

    def _handle_pubsub_dispatch_ack(self, envelope: Dict[str, Any]) -> None:
        """Update origin-worker inflight state when the remote worker sends ACK."""
        execution_id = envelope.get("execution_id", "")
        inflight = self._inflight.get(execution_id)
        if not inflight:
            return

        inflight.acked = True
        inflight.client_id = envelope.get("client_id", inflight.client_id)
        inflight.last_progress_at = time.monotonic()

    def _handle_pubsub_dispatch_progress(self, envelope: Dict[str, Any]) -> None:
        """Update origin-worker progress from a remote worker."""
        execution_id = envelope.get("execution_id", "")
        inflight = self._inflight.get(execution_id)
        if not inflight:
            return

        inflight.last_progress_pct = envelope.get(
            "progress_pct",
            inflight.last_progress_pct,
        )
        inflight.last_progress_msg = envelope.get(
            "message",
            inflight.last_progress_msg,
        )
        inflight.last_progress_at = time.monotonic()

    def _handle_pubsub_dispatch_result(self, envelope: Dict[str, Any]) -> None:
        """Resolve the origin-worker future when the remote worker completes."""
        execution_id = envelope.get("execution_id", "")
        inflight = self._inflight.pop(execution_id, None)
        if not inflight:
            return

        result = envelope.get("result") or {
            "execution_id": execution_id,
            "status": "failed",
            "error": "Remote worker returned no result payload",
        }

        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)

        self._completed[execution_id] = time.monotonic()
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)

    def _handle_pubsub_dispatch_failed(self, envelope: Dict[str, Any]) -> None:
        """Fallback from pub/sub relay to DB polling if the remote path breaks."""
        execution_id = envelope.get("execution_id", "")
        inflight = self._inflight.pop(execution_id, None)
        if not inflight:
            return

        result = {
            "execution_id": execution_id,
            "status": "retry_db",
            "error": envelope.get("error", "Remote worker dispatch failed"),
            "retry_transport": envelope.get("retry_transport", "db_polling"),
        }
        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)
