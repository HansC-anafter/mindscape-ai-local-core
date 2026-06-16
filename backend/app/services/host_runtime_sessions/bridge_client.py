"""Host-side Host Runtime Session bridge client."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
from typing import Any, Awaitable, Callable

import websockets

from backend.app.services.external_agents.bridge.task_executor import HostBridgeTaskExecutor

from .bridge_protocol import (
    HostRuntimeTurnContext,
    build_bridge_event_message,
    build_completion_event_messages,
    build_executor_dispatch,
    elapsed_seconds,
    monotonic_started_at,
)

logger = logging.getLogger("host_runtime_session_bridge")

EmitMessage = Callable[[dict[str, Any]], Awaitable[None]]
ExecutorFactory = Callable[[Callable[[str, int, str], Awaitable[None]]], Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]]


class HostRuntimeDirectCodexTaskExecutor(HostBridgeTaskExecutor):
    """Codex executor for the local-terminal Host Runtime Session path.

    The legacy shared bridge resolves Codex auth through the backend runtime pool.
    The AOL graph host-runtime surface intentionally mirrors a local terminal
    Codex CLI session, so it must use the host process' own Codex auth state and
    avoid pool auth probes for every turn.
    """

    async def _fetch_runtime_auth_env(
        self,
        runtime_name: str,
        ctx: Any,
        *,
        excluded_runtime_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "env": {},
            "selected_runtime_id": "host_runtime_direct_codex_cli",
            "effective_workspace_id": getattr(ctx, "workspace_id", "") or "",
        }

    async def _report_runtime_quota_exhausted(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def _report_runtime_auth_failure(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def _report_runtime_success(self, *args: Any, **kwargs: Any) -> None:
        return None


def backend_api_url_from_host(host: str) -> str:
    raw = str(host or "").strip() or "localhost:8200"
    if raw.startswith(("http://", "https://")):
        return raw.rstrip("/")
    return f"http://{raw}".rstrip("/")


def websocket_url_from_host(host: str, bridge_id: str) -> str:
    raw = str(host or "").strip() or "localhost:8200"
    if raw.startswith("https://"):
        raw = "wss://" + raw[len("https://") :]
    elif raw.startswith("http://"):
        raw = "ws://" + raw[len("http://") :]
    elif not raw.startswith(("ws://", "wss://")):
        raw = f"ws://{raw}"
    return f"{raw.rstrip('/')}/api/v1/host-runtime/bridge/{bridge_id}"


class HostRuntimeTurnRunner:
    def __init__(
        self,
        *,
        emit_message: EmitMessage,
        executor_factory: ExecutorFactory,
        max_duration: int = 600,
        model: str = "",
    ) -> None:
        self._emit_message = emit_message
        self._executor_factory = executor_factory
        self._max_duration = max_duration
        self._model = model

    async def run_turn(self, message: dict[str, Any]) -> None:
        context = HostRuntimeTurnContext.from_turn_start(message)
        if not context.execution_id or not context.workspace_id or not context.session_id or not context.turn_id:
            logger.warning("Ignoring malformed turn.start payload: %s", message)
            return

        async def progress_callback(execution_id: str, percent: int, detail: str) -> None:
            if execution_id != context.execution_id:
                return
            await self._emit_message(
                build_bridge_event_message(
                    context,
                    "tool.output.delta",
                    {
                        "percent": int(percent),
                        "message": str(detail or ""),
                        "source": "host_runtime_bridge",
                    },
                    item_id=f"progress_{context.turn_id}",
                )
            )

        executor = self._executor_factory(progress_callback)
        dispatch = build_executor_dispatch(
            context,
            max_duration=self._max_duration,
            model=self._model,
        )
        await self._emit_message(
            build_bridge_event_message(
                context,
                "item.started",
                {
                    "kind": "host_runtime_cli_turn",
                    "runtime_surface": context.runtime_surface,
                    "runtime_id": context.runtime_id,
                },
                item_id=f"turn_{context.turn_id}",
            )
        )

        started_at = monotonic_started_at()
        try:
            result = await executor(dispatch)
        except asyncio.CancelledError:
            result = {
                "status": "cancelled",
                "error": "Host runtime turn was cancelled",
            }
        except Exception as exc:
            logger.exception("Host runtime turn failed before executor result")
            result = {
                "status": "failed",
                "error": str(exc),
            }

        duration = elapsed_seconds(started_at)
        for event_message in build_completion_event_messages(
            context,
            result if isinstance(result, dict) else {"status": "failed", "error": str(result)},
            duration_seconds=duration,
        ):
            await self._emit_message(event_message)


class HostRuntimeSessionBridgeClient:
    HEARTBEAT_SECONDS = 20.0
    RECONNECT_SECONDS = 2.0

    def __init__(
        self,
        *,
        host: str,
        bridge_id: str,
        workspace_ids: list[str],
        runtime_surface: str = "codex_cli",
        runtime_id: str = "codex_cli",
        workspace_root: str = "",
        max_duration: int = 600,
        model: str = "",
        executor_factory: ExecutorFactory | None = None,
    ) -> None:
        self.host = host
        self.bridge_id = bridge_id
        self.workspace_ids = [item for item in workspace_ids if item]
        self.runtime_surface = runtime_surface
        self.runtime_id = runtime_id
        self.workspace_root = workspace_root or os.getcwd()
        self.max_duration = max_duration
        self.model = model
        self._executor_factory = executor_factory or self._default_executor_factory
        self._running = False
        self._ws: Any = None
        self._send_lock = asyncio.Lock()
        self._turn_lock = asyncio.Lock()
        self._active_turn_task: asyncio.Task[None] | None = None

    @property
    def ws_url(self) -> str:
        return websocket_url_from_host(self.host, self.bridge_id)

    def _default_executor_factory(
        self,
        progress_callback: Callable[[str, int, str], Awaitable[None]],
    ) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
        executor_cls = (
            HostRuntimeDirectCodexTaskExecutor
            if self.runtime_surface == "codex_cli"
            else HostBridgeTaskExecutor
        )
        return executor_cls(
            workspace_root=self.workspace_root,
            runtime_surface=self.runtime_surface,
            progress_callback=progress_callback,
        )

    async def run(self) -> None:
        self._running = True
        os.environ.setdefault("MINDSCAPE_BACKEND_API_URL", backend_api_url_from_host(self.host))
        os.environ.setdefault("MINDSCAPE_WS_HOST", str(self.host or "localhost:8200"))
        while self._running:
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._running:
                    return
                logger.warning("Host runtime bridge reconnecting after error: %s", exc)
                await asyncio.sleep(self.RECONNECT_SECONDS)

    async def stop(self) -> None:
        self._running = False
        if self._active_turn_task and not self._active_turn_task.done():
            self._active_turn_task.cancel()
            await asyncio.gather(self._active_turn_task, return_exceptions=True)
        if self._ws is not None:
            await self._ws.close()

    async def _connect_once(self) -> None:
        logger.info("Connecting Host Runtime Session bridge to %s", self.ws_url)
        async with websockets.connect(self.ws_url, open_timeout=30, ping_interval=20, ping_timeout=120) as ws:
            self._ws = ws
            await self._register()
            heartbeat = asyncio.create_task(self._heartbeat_loop())
            try:
                async for raw_message in ws:
                    await self._handle_raw_message(raw_message)
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                self._ws = None

    async def _register(self) -> None:
        await self._send(
            {
                "type": "register",
                "runtime_surface": self.runtime_surface,
                "runtime_id": self.runtime_id,
                "workspace_ids": self.workspace_ids,
                "capabilities": {
                    "protocol": "host_runtime_session.v1",
                    "stream_events": True,
                    "executor": (
                        "HostRuntimeDirectCodexTaskExecutor"
                        if self.runtime_surface == "codex_cli"
                        else "HostBridgeTaskExecutor"
                    ),
                },
            }
        )

    async def _heartbeat_loop(self) -> None:
        while self._running and self._ws is not None:
            await asyncio.sleep(self.HEARTBEAT_SECONDS)
            await self._send({"type": "ping"})

    async def _handle_raw_message(self, raw_message: str | bytes) -> None:
        try:
            message = json.loads(raw_message)
        except (TypeError, ValueError):
            logger.warning("Ignoring non-JSON bridge message: %r", raw_message)
            return
        message_type = str(message.get("type") or "")
        if message_type in {"welcome", "registered", "pong", "event_ack"}:
            return
        if message_type == "turn.start":
            await self._start_turn(message)
            return
        if message_type == "session.interrupt":
            await self._interrupt_turn(message)
            return
        if message_type == "approval.resolve":
            logger.info("Approval resolution received for %s", message.get("approval_id"))
            return
        if message_type == "error":
            logger.warning("Bridge server error: %s", message.get("detail") or message.get("error"))
            return
        logger.warning("Unsupported Host Runtime Session bridge message: %s", message_type)

    async def _start_turn(self, message: dict[str, Any]) -> None:
        async with self._turn_lock:
            if self._active_turn_task and not self._active_turn_task.done():
                context = HostRuntimeTurnContext.from_turn_start(message)
                await self._send(
                    build_bridge_event_message(
                        context,
                        "turn.failed",
                        {"reason": "bridge_busy"},
                    )
                )
                return
            runner = HostRuntimeTurnRunner(
                emit_message=self._send,
                executor_factory=self._executor_factory,
                max_duration=self.max_duration,
                model=self.model,
            )
            self._active_turn_task = asyncio.create_task(runner.run_turn(message))
            self._active_turn_task.add_done_callback(lambda _task: setattr(self, "_active_turn_task", None))

    async def _interrupt_turn(self, message: dict[str, Any]) -> None:
        task = self._active_turn_task
        if task and not task.done():
            task.cancel()
        logger.info("Host runtime session interrupt received: %s", message.get("reason") or "")

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("Host runtime bridge websocket is not connected")
        async with self._send_lock:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))


def parse_workspace_ids(raw_values: list[str]) -> list[str]:
    workspace_ids: list[str] = []
    for raw_value in raw_values:
        for item in str(raw_value or "").split(","):
            candidate = item.strip()
            if candidate and candidate not in workspace_ids:
                workspace_ids.append(candidate)
    return workspace_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Host Runtime Session bridge client")
    parser.add_argument("--host", default=os.environ.get("MINDSCAPE_WS_HOST", "localhost:8200"))
    parser.add_argument("--bridge-id", default=os.environ.get("HOST_RUNTIME_BRIDGE_ID", ""))
    parser.add_argument("--workspace-id", action="append", default=[])
    parser.add_argument("--runtime-surface", default=os.environ.get("HOST_RUNTIME_SURFACE", "codex_cli"))
    parser.add_argument("--runtime-id", default=os.environ.get("HOST_RUNTIME_ID", "codex_cli"))
    parser.add_argument("--workspace-root", default=os.environ.get("MINDSCAPE_WORKSPACE_ROOT", os.getcwd()))
    parser.add_argument("--max-duration", type=int, default=int(os.environ.get("HOST_RUNTIME_MAX_DURATION", "600")))
    parser.add_argument("--model", default=os.environ.get("HOST_RUNTIME_MODEL", ""))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    bridge_id = args.bridge_id.strip() or f"hostrt-{args.runtime_surface}-{os.getpid()}"
    workspace_ids = parse_workspace_ids(args.workspace_id or [os.environ.get("MINDSCAPE_WORKSPACE_ID", "")])
    client = HostRuntimeSessionBridgeClient(
        host=args.host,
        bridge_id=bridge_id,
        workspace_ids=workspace_ids,
        runtime_surface=args.runtime_surface,
        runtime_id=args.runtime_id,
        workspace_root=args.workspace_root,
        max_duration=args.max_duration,
        model=args.model,
    )

    loop = asyncio.new_event_loop()

    def shutdown(_sig: signal.Signals) -> None:
        loop.create_task(client.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: shutdown(s))
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame, s=sig: shutdown(s))

    try:
        loop.run_until_complete(client.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
