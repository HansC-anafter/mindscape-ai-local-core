"""Redis lifecycle for the sole workspace event SSE route."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.services.cache.async_redis import get_async_redis_client
from backend.app.services.workspace_event_lifecycle import workspace_event_channel


class WorkspaceEventStreamUnavailable(RuntimeError):
    pass


class WorkspaceEventSubscription:
    def __init__(
        self,
        *,
        workspace_id: str,
        listener: Any,
        subscribed_at: datetime,
    ) -> None:
        self.workspace_id = workspace_id
        self.listener = listener
        self.subscribed_at = subscribed_at
        self.closed = False

    async def next_payload(self, *, timeout_seconds: float) -> Optional[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(float(timeout_seconds), 0.01)
        while not self.closed:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                message = await self.listener.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(remaining, 5.0),
                )
            except Exception as exc:
                raise WorkspaceEventStreamUnavailable(
                    "workspace_event_subscription_receive_failed"
                ) from exc
            if not message:
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if not isinstance(raw, str):
                return {}
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
        return None

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await self.listener.unsubscribe(workspace_event_channel(self.workspace_id))
        finally:
            await self.listener.close()


async def open_workspace_event_subscription(
    workspace_id: str,
) -> WorkspaceEventSubscription:
    try:
        client = await get_async_redis_client()
        if client is None:
            raise WorkspaceEventStreamUnavailable("workspace_event_redis_unavailable")
        listener = client.pubsub(ignore_subscribe_messages=True)
        await listener.subscribe(workspace_event_channel(workspace_id))
        return WorkspaceEventSubscription(
            workspace_id=workspace_id,
            listener=listener,
            subscribed_at=datetime.now(timezone.utc),
        )
    except WorkspaceEventStreamUnavailable:
        raise
    except Exception as exc:
        raise WorkspaceEventStreamUnavailable(
            "workspace_event_redis_unavailable"
        ) from exc


__all__ = [
    "WorkspaceEventStreamUnavailable",
    "WorkspaceEventSubscription",
    "open_workspace_event_subscription",
]
