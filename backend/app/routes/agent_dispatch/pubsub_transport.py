"""
Agent Dispatch -- Redis pub/sub transport layer.

Manages the async Redis client, pub/sub subscribe/publish lifecycle,
and worker identity helpers.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

from .connection_manager import _get_worker_instance_id

logger = logging.getLogger(__name__)


class PubSubTransportMixin:
    """Mixin: Redis pub/sub client management and I/O."""

    PUBSUB_CHANNEL_PREFIX = "mindscape:agent-dispatch:worker"

    def _ensure_worker_identity(self) -> str:
        """Refresh worker identity after fork/reload and return it."""
        current = _get_worker_instance_id()
        if getattr(self, "_worker_instance_id", None) != current:
            self._worker_instance_id = current
        return self._worker_instance_id

    def _worker_channel(self, worker_instance_id: Optional[str] = None) -> str:
        """Return the Redis pub/sub channel for a worker instance."""
        worker = worker_instance_id or self._ensure_worker_identity()
        return f"{self.PUBSUB_CHANNEL_PREFIX}:{worker}"

    def _redis_pubsub_enabled(self) -> bool:
        """Check whether Redis pub/sub cross-worker transport is enabled."""
        return (
            os.getenv(
                "AGENT_DISPATCH_REDIS_PUBSUB_ENABLED",
                os.getenv("REDIS_ENABLED", "true"),
            ).lower()
            == "true"
        )

    async def _get_async_redis_client(self):
        """Get an async Redis client for pub/sub."""
        if not self._redis_pubsub_enabled():
            self._pubsub_available = False
            return None

        client = getattr(self, "_pubsub_client", None)
        if client is not None:
            try:
                await client.ping()
                self._pubsub_available = True
                return client
            except Exception:
                self._pubsub_client = None

        try:
            from redis.asyncio import Redis

            client = Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD") or None,
                db=int(os.getenv("REDIS_DB", "0")),
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            await client.ping()
            self._pubsub_client = client
            self._pubsub_available = True
            logger.info(
                "[AgentWS] Redis pub/sub connected for worker %s",
                self._ensure_worker_identity(),
            )
            return client
        except Exception as exc:
            self._pubsub_available = False
            logger.warning(
                "[AgentWS] Redis pub/sub unavailable for worker %s: %s",
                self._ensure_worker_identity(),
                exc,
            )
            return None

    def start_pubsub_listener(self) -> None:
        """Start the Redis pub/sub listener for this worker."""
        if self._pubsub_task and not self._pubsub_task.done():
            return

        try:
            loop = asyncio.get_event_loop()
            self._pubsub_task = loop.create_task(self.consume_pubsub_events())
            logger.info(
                "[AgentWS] Redis pub/sub listener starting for worker %s",
                self._ensure_worker_identity(),
            )
        except Exception:
            logger.exception("[AgentWS] Failed to start Redis pub/sub listener")

    def stop_pubsub_listener(self) -> None:
        """Stop the Redis pub/sub listener for this worker."""
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            self._pubsub_task = None
            logger.info(
                "[AgentWS] Redis pub/sub listener stopped for worker %s",
                self._ensure_worker_identity(),
            )

    async def consume_pubsub_events(self) -> None:
        """Background task: subscribe to worker-targeted Redis messages."""
        worker_id = self._ensure_worker_identity()

        while True:
            listener = None
            try:
                client = await self._get_async_redis_client()
                if not client:
                    await asyncio.sleep(2.0)
                    continue

                listener = client.pubsub(ignore_subscribe_messages=True)
                self._pubsub_listener = listener
                await listener.subscribe(self._worker_channel(worker_id))
                logger.info(
                    "[AgentWS] Redis pub/sub subscribed on %s",
                    self._worker_channel(worker_id),
                )

                while True:
                    message = await listener.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if not message:
                        await asyncio.sleep(0.1)
                        continue

                    raw_data = message.get("data")
                    if not raw_data:
                        continue
                    if not isinstance(raw_data, str):
                        raw_data = str(raw_data)

                    try:
                        envelope = json.loads(raw_data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "[AgentWS] Ignoring invalid pub/sub payload: %r",
                            raw_data[:200],
                        )
                        continue

                    await self._handle_pubsub_envelope(envelope)

            except asyncio.CancelledError:
                raise
            except Exception:
                self._pubsub_available = False
                logger.exception(
                    "[AgentWS] Redis pub/sub listener crashed for worker %s",
                    worker_id,
                )
                await asyncio.sleep(2.0)
            finally:
                if listener is not None:
                    try:
                        await listener.unsubscribe(self._worker_channel(worker_id))
                        await listener.close()
                    except Exception:
                        pass
                self._pubsub_listener = None

    async def _publish_pubsub_message(
        self,
        target_worker_id: str,
        envelope: Dict[str, Any],
    ) -> bool:
        """Publish a message to another worker's Redis channel."""
        client = await self._get_async_redis_client()
        if not client:
            return False

        payload = json.dumps(envelope)
        try:
            subscribers = await client.publish(
                self._worker_channel(target_worker_id),
                payload,
            )
            if subscribers < 1:
                logger.warning(
                    "[AgentWS] Pub/sub publish had no subscribers for %s "
                    "(type=%s, exec=%s)",
                    target_worker_id,
                    envelope.get("type"),
                    envelope.get("execution_id"),
                )
                return False
            return True
        except Exception:
            self._pubsub_available = False
            logger.exception(
                "[AgentWS] Failed to publish pub/sub message to worker %s",
                target_worker_id,
            )
            return False
