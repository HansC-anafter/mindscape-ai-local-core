"""
Agent Dispatch -- Cross-worker dispatch mixin.

Primary path:
  Redis pub/sub between workers, with the socket-owning worker relaying
  ack/progress/result events back to the origin worker.

Fallback path:
  PostgreSQL pending_dispatch polling when Redis is unavailable or a
  worker-to-worker publish cannot be guaranteed.

Implementation is split across focused sub-modules:
  - pubsub_transport: Redis client lifecycle and pub/sub I/O
  - pubsub_handlers:  envelope routing and event handlers
  - db_fallback:      PostgreSQL pending_dispatch transport
"""

import asyncio
import time
from typing import Any, Dict, Optional

from .pubsub_transport import PubSubTransportMixin
from .pubsub_handlers import PubSubHandlersMixin
from .db_fallback import DbFallbackMixin

from .models import InflightTask


class CrossWorkerMixin(
    PubSubTransportMixin,
    PubSubHandlersMixin,
    DbFallbackMixin,
):
    """Mixin: Redis pub/sub cross-worker dispatch with DB fallback.

    Composes three focused sub-mixins and adds the top-level dispatch
    orchestration methods.
    """

    async def _await_inflight_result(
        self,
        execution_id: str,
        result_future: asyncio.Future,
        timeout: float,
        context_label: str,
    ) -> Dict[str, Any]:
        """Wait for a task result while treating progress as activity."""
        last_activity = time.monotonic()

        while True:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(result_future),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                inflight = self._inflight.get(execution_id)
                if inflight and inflight.last_progress_at > last_activity:
                    last_activity = inflight.last_progress_at

                idle = time.monotonic() - last_activity
                if idle > timeout:
                    self._inflight.pop(execution_id, None)
                    return {
                        "execution_id": execution_id,
                        "status": "timeout",
                        "error": f"No activity for {idle:.0f}s ({context_label})",
                    }

    async def _try_pubsub_dispatch(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        timeout: float,
        target_client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Try Redis pub/sub dispatch to the worker that owns the WS client."""
        if not self._redis_pubsub_enabled():
            return None

        self.start_pubsub_listener()
        target = await asyncio.to_thread(
            self._db_get_dispatch_target,
            workspace_id,
            target_client_id,
        )
        if not target:
            return None

        target_worker_id = target.get("worker_instance_id")
        target_client_id = target.get("client_id")
        if not target_worker_id:
            return None

        if target_worker_id == self._ensure_worker_identity():
            # DB row says the client belongs here, but local lookup failed.
            # Treat as stale registry data and fall back.
            return None

        loop = asyncio.get_event_loop()
        result_future: asyncio.Future = loop.create_future()
        inflight = InflightTask(
            execution_id=execution_id,
            workspace_id=workspace_id,
            client_id=target_client_id or "remote",
            origin_worker_id=self._ensure_worker_identity(),
            result_future=result_future,
            payload=message,
            thread_id=(message.get("context") or {}).get("thread_id"),
            project_id=(message.get("context") or {}).get("project_id"),
        )
        self._inflight[execution_id] = inflight

        published = await self._publish_pubsub_message(
            target_worker_id,
            {
                "type": "dispatch_request",
                "execution_id": execution_id,
                "workspace_id": workspace_id,
                "client_id": target_client_id,
                "origin_worker_id": self._ensure_worker_identity(),
                "payload": message,
            },
        )
        if not published:
            self._inflight.pop(execution_id, None)
            return None

        result = await self._await_inflight_result(
            execution_id,
            result_future,
            timeout,
            context_label="redis-pubsub",
        )
        if result.get("status") == "retry_db":
            return None
        return result

    async def _cross_worker_dispatch(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        timeout: float = 600.0,
        target_client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a task via Redis pub/sub, falling back to DB polling."""
        result = await self._try_pubsub_dispatch(
            workspace_id=workspace_id,
            message=message,
            execution_id=execution_id,
            timeout=timeout,
            target_client_id=target_client_id,
        )
        if result is not None:
            return result

        return await self._cross_worker_dispatch_via_db(
            workspace_id=workspace_id,
            message=message,
            execution_id=execution_id,
            timeout=timeout,
        )
