"""In-memory host runtime bridge registry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .models import HostRuntimeBridgeSnapshot, HostRuntimeExecutionEnvelope, utc_now


@dataclass
class HostRuntimeBridgeConnection:
    bridge_id: str
    websocket: Any
    runtime_surface: str = "codex_cli"
    runtime_id: str = "codex_cli"
    workspace_ids: set[str] = field(default_factory=set)
    capabilities: dict[str, Any] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connected_at: Any = field(default_factory=utc_now)
    last_heartbeat_at: Any = field(default_factory=utc_now)

    def snapshot(self) -> HostRuntimeBridgeSnapshot:
        return HostRuntimeBridgeSnapshot(
            bridge_id=self.bridge_id,
            runtime_surface=self.runtime_surface,  # type: ignore[arg-type]
            runtime_id=self.runtime_id,
            workspace_ids=sorted(self.workspace_ids),
            connected_at=self.connected_at,
            last_heartbeat_at=self.last_heartbeat_at,
            capabilities=self.capabilities,
        )


class HostRuntimeBridgeRegistry:
    def __init__(self) -> None:
        self._bridges: dict[str, HostRuntimeBridgeConnection] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        *,
        bridge_id: str,
        websocket: Any,
        runtime_surface: str = "codex_cli",
        runtime_id: str = "codex_cli",
        workspace_ids: list[str] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> HostRuntimeBridgeConnection:
        connection = HostRuntimeBridgeConnection(
            bridge_id=bridge_id,
            websocket=websocket,
            runtime_surface=runtime_surface,
            runtime_id=runtime_id,
            workspace_ids=set(workspace_ids or []),
            capabilities=capabilities or {},
        )
        async with self._lock:
            self._bridges[bridge_id] = connection
        return connection

    async def unregister(self, bridge_id: str) -> None:
        async with self._lock:
            self._bridges.pop(bridge_id, None)

    async def mark_heartbeat(self, bridge_id: str) -> None:
        async with self._lock:
            connection = self._bridges.get(bridge_id)
            if connection:
                connection.last_heartbeat_at = utc_now()

    async def snapshots(self) -> list[HostRuntimeBridgeSnapshot]:
        async with self._lock:
            return [connection.snapshot() for connection in self._bridges.values()]

    async def get(self, bridge_id: str) -> HostRuntimeBridgeConnection | None:
        async with self._lock:
            return self._bridges.get(bridge_id)

    async def select_bridge(
        self,
        *,
        workspace_id: str,
        runtime_surface: str,
        runtime_id: str | None = None,
    ) -> HostRuntimeBridgeConnection | None:
        async with self._lock:
            candidates = list(self._bridges.values())
        matching: list[HostRuntimeBridgeConnection] = []
        for connection in candidates:
            if connection.runtime_surface != runtime_surface:
                continue
            if runtime_id and connection.runtime_id != runtime_id:
                continue
            if connection.workspace_ids and workspace_id not in connection.workspace_ids:
                continue
            matching.append(connection)
        if not matching:
            return None

        def priority(connection: HostRuntimeBridgeConnection) -> tuple[int, float, float]:
            workspace_specific = 1 if workspace_id in connection.workspace_ids else 0
            return (
                workspace_specific,
                connection.last_heartbeat_at.timestamp(),
                connection.connected_at.timestamp(),
            )

        return max(matching, key=priority)

    async def dispatch_turn(
        self,
        *,
        bridge: HostRuntimeBridgeConnection,
        prompt: str,
        envelope: HostRuntimeExecutionEnvelope,
    ) -> None:
        payload = {
            "type": "turn.start",
            "workspace_id": envelope.workspace_id,
            "session_id": envelope.session_id,
            "turn_id": envelope.turn_id,
            "runtime_surface": envelope.runtime_surface,
            "runtime_id": envelope.runtime_id,
            "prompt": prompt,
            "envelope": envelope.model_dump(mode="json"),
        }
        async with bridge.send_lock:
            await bridge.websocket.send_json(payload)


_bridge_registry = HostRuntimeBridgeRegistry()


def get_host_runtime_bridge_registry() -> HostRuntimeBridgeRegistry:
    return _bridge_registry
