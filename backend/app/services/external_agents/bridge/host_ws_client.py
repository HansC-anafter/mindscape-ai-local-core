"""
Host-side WebSocket client for shared CLI surfaces.

This script runs in the host environment to:
  1. Connect to the Mindscape backend via WebSocket
  2. Authenticate using HMAC challenge-response
  3. Receive dispatched coding tasks
  4. Execute tasks via the surface-specific CLI runtime
  5. Send back ack, progress, and result messages

Usage:
    python host_ws_client.py --workspace-id ws-123 [--host localhost:8000]
    python host_ws_client.py --workspace-id ws-123 --auth-secret my_secret

Environment Variables:
    MINDSCAPE_WS_HOST       Backend host (default: localhost:8000)
    MINDSCAPE_AUTH_SECRET    HMAC auth secret (optional, skipped in dev mode)
    MINDSCAPE_WORKSPACE_ID  Workspace ID
"""

import argparse
import asyncio
import copy
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict
from typing import Any, Callable, Coroutine, Dict, Optional, Set

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("host_ws_client")


class HostBridgeWSClient:
    """
    Host-side WebSocket client for receiving and executing tasks
    from the Mindscape backend.
    """

    # Reconnect settings
    RECONNECT_BASE_DELAY: float = 1.0
    RECONNECT_MAX_DELAY: float = 30.0
    RECONNECT_MAX_ATTEMPTS: int = 0  # 0 = unlimited

    # Heartbeat interval (should be < server's CLIENT_TIMEOUT)
    HEARTBEAT_INTERVAL: float = 25.0
    # Pong response timeout — if server doesn't respond within this,
    # the connection is considered dead (e.g. backend restarted).
    PONG_TIMEOUT: float = 10.0
    # WS result should be acknowledged quickly; otherwise fall back
    # to the REST result endpoint so the execution does not remain stuck.
    RESULT_ACK_TIMEOUT: float = 5.0
    RESULT_REST_RETRY_ATTEMPTS: int = 4
    RESULT_REST_RETRY_BASE_DELAY: float = 1.0
    # Keep recently delivered results around long enough to survive a
    # reconnect/re-dispatch cycle without re-running the same task.
    RECENT_RESULT_TTL: float = 600.0
    RECENT_RESULT_MAX_SIZE: int = 256

    def __init__(
        self,
        workspace_id: str,
        host: str = "localhost:8000",
        auth_secret: Optional[str] = None,
        client_id: Optional[str] = None,
        surface: str = "gemini_cli",
        task_handler: Optional[Callable] = None,
    ):
        self.workspace_id = workspace_id
        self.host = host
        self.auth_secret = auth_secret
        self.client_id = client_id or str(uuid.uuid4())
        self.surface = surface
        self.task_handler = task_handler or self._default_task_handler

        self._ws = None
        self._running = False
        self._reconnect_attempt = 0
        self._pong_received = asyncio.Event()
        self._active_tasks = 0  # suppress pong-timeout during execution
        self._result_ack_waiters: Dict[str, asyncio.Future[bool]] = {}
        self._background_tasks: Set[asyncio.Task] = set()
        self._recent_results: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = (
            OrderedDict()
        )

    @property
    def ws_url(self) -> str:
        """Build WebSocket URL."""
        return (
            f"ws://{self.host}/ws/agent/{self.workspace_id}"
            f"?client_id={self.client_id}&surface={self.surface}"
        )

    # ============================================================
    #  Main lifecycle
    # ============================================================

    def _preflight_check(self) -> None:
        """Validate runtime env before connecting.

        For gemini_cli, verify the provider-specific bridge command exists.
        For all surfaces, ensure some auth path or backend token endpoint
        is available so the process never registers as "connected" in the
        backend with an unusable runtime.
        """
        runtime_cmd = ""
        if self.surface == "gemini_cli":
            runtime_cmd = os.environ.get("GEMINI_CLI_RUNTIME_CMD", "").strip()
            if not runtime_cmd:
                raise RuntimeError(
                    "GEMINI_CLI_RUNTIME_CMD is not set. "
                    "Start this client via scripts/start_cli_bridge.sh "
                    "or scripts/start_ws_bridge.sh which set the required "
                    "Gemini bridge command."
                )

            import shlex as _shlex
            import os as _os

            # posix=False on Windows: preserve backslashes in paths
            argv = _shlex.split(runtime_cmd, posix=(_os.name != 'nt'))
            # Must have at least 2 tokens: interpreter + script path
            if len(argv) < 2:
                raise RuntimeError(
                    f"GEMINI_CLI_RUNTIME_CMD is incomplete ('{runtime_cmd}'). "
                    "Expected format: "
                    "'python3 /path/to/gemini_cli_runtime_bridge.py'."
                )

        has_backend = bool(os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip())
        auth_mode = "backend_api" if has_backend else ""
        if self.surface == "codex_cli":
            if os.environ.get("OPENAI_API_KEY", "").strip():
                auth_mode = "api_key"
        elif self.surface == "claude_code_cli":
            if os.environ.get("ANTHROPIC_API_KEY", "").strip():
                auth_mode = "api_key"
        else:
            if os.environ.get("GEMINI_API_KEY", "").strip():
                auth_mode = "api_key"
            elif (
                os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
                == "true"
            ):
                auth_mode = "vertex_ai"
            elif (
                os.environ.get("GOOGLE_GENAI_USE_GCA", "").strip().lower() == "true"
            ):
                auth_mode = "gca"

        if not auth_mode:
            raise RuntimeError(
                f"No auth configured for surface '{self.surface}'. "
                "Provide the provider-specific API key or configure "
                "MINDSCAPE_BACKEND_API_URL so the backend can issue CLI auth."
            )

        logger.info(
            "Preflight OK: surface=%s runtime_cmd=%r auth_mode=%s",
            self.surface,
            runtime_cmd or None,
            auth_mode,
        )

    async def run(self) -> None:
        """Main entry point -- connect with auto-reconnect."""
        self._preflight_check()
        self._running = True
        logger.info(
            "Starting host bridge WS client (workspace=%s surface=%s)",
            self.workspace_id,
            self.surface,
        )

        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                if not self._running:
                    break
                delay = self._backoff_delay()
                logger.warning(
                    f"Connection lost: {e}. "
                    f"Reconnecting in {delay:.1f}s "
                    f"(attempt {self._reconnect_attempt})..."
                )
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._ws:
            await self._ws.close()
        logger.info("Host bridge WS client stopped")

    # ============================================================
    #  Connection
    # ============================================================

    async def _connect_and_listen(self) -> None:
        """Single connection lifecycle."""
        logger.info(f"Connecting to {self.ws_url}")

        # Use protocol-level ping/pong as a safety net for dead TCP.
        # If backend restarts and TCP silently dies, the protocol
        # ping will timeout → ConnectionClosed → reconnect.
        async with websockets.connect(
            self.ws_url,
            ping_interval=20,
            ping_timeout=120,  # long timeout to survive task execution
        ) as ws:
            self._ws = ws
            self._reconnect_attempt = 0
            logger.info("Connected!")

            # Start heartbeat task
            heartbeat = asyncio.create_task(self._heartbeat_loop())

            try:
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        # Handle server pong for app-level liveness
                        if msg.get("type") == "pong":
                            self._pong_received.set()
                            continue
                        await self._handle_message(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {raw_msg[:100]}")
            finally:
                heartbeat.cancel()
                self._ws = None

    async def _heartbeat_loop(self) -> None:
        """Send periodic pings and verify server responds.

        After backend restart, TCP may stay alive but the server-side
        WS state is gone. We send an app-level ping and wait for a
        pong response within PONG_TIMEOUT. If no pong arrives, we
        force-close the WebSocket to trigger reconnect.

        IMPORTANT: During active task execution, we skip the pong-or-die
        check because the server may be busy and slow to respond.
        """
        while True:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            if not self._ws:
                break
            try:
                self._pong_received.clear()
                await self._ws.send(json.dumps({"type": "ping"}))
                # Wait for server pong within timeout
                try:
                    await asyncio.wait_for(
                        self._pong_received.wait(),
                        timeout=self.PONG_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    if self._active_tasks > 0:
                        logger.info(
                            f"Pong timeout but {self._active_tasks} task(s) "
                            f"active — keeping connection alive"
                        )
                        continue
                    logger.warning(
                        f"Server did not respond to ping within "
                        f"{self.PONG_TIMEOUT}s — connection is stale, "
                        f"forcing reconnect"
                    )
                    await self._ws.close()
                    break
            except Exception:
                break

    def _backoff_delay(self) -> float:
        """Exponential backoff with jitter."""
        import random

        self._reconnect_attempt += 1
        delay = min(
            self.RECONNECT_BASE_DELAY * (2 ** (self._reconnect_attempt - 1)),
            self.RECONNECT_MAX_DELAY,
        )
        return delay + random.uniform(0, delay * 0.1)

    # ============================================================
    #  Message handling
    # ============================================================

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """Route incoming messages by type."""
        msg_type = msg.get("type", "")

        if msg_type == "auth_challenge":
            await self._handle_auth_challenge(msg)
        elif msg_type == "welcome":
            logger.info(
                f"Welcome! client_id={msg.get('client_id')}, "
                f"flushed={msg.get('flushed_tasks', 0)} pending tasks"
            )
        elif msg_type == "auth_ok":
            logger.info(f"Authenticated! flushed={msg.get('flushed_tasks', 0)} tasks")
        elif msg_type == "auth_failed":
            logger.error(f"Auth failed: {msg.get('error')}")
            await self.stop()
        elif msg_type == "dispatch":
            await self._handle_dispatch(msg)
        elif msg_type == "pong":
            pass  # Heartbeat response
        elif msg_type == "result_ack":
            execution_id = msg.get("execution_id", "")
            waiter = self._result_ack_waiters.pop(execution_id, None)
            if waiter and not waiter.done():
                waiter.set_result(True)
            logger.debug(f"Result acknowledged: {msg.get('execution_id')}")
        elif msg_type == "error":
            logger.error(f"Server error: {msg.get('error')}")
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_auth_challenge(self, msg: Dict[str, Any]) -> None:
        """Respond to HMAC auth challenge."""
        nonce = msg.get("nonce", "")

        if not self.auth_secret:
            logger.warning("Auth challenge received but no auth_secret configured")
            return

        nonce_response = hmac.new(
            self.auth_secret.encode(),
            (nonce + self.client_id).encode(),
            hashlib.sha256,
        ).hexdigest()

        await self._send(
            {
                "type": "auth_response",
                "token": self.auth_secret,  # Pre-shared token
                "nonce_response": nonce_response,
            }
        )
        logger.info("Auth response sent")

    async def _handle_dispatch(self, msg: Dict[str, Any]) -> None:
        """
        Handle a dispatched task.

        1. Send ack
        2. Execute task via task_handler
        3. Send result
        """
        execution_id = msg.get("execution_id", "")
        task = msg.get("task", "")

        logger.info(f"Task received: exec={execution_id}, task={task[:80]}...")

        # 1. Acknowledge
        await self._send(
            {
                "type": "ack",
                "execution_id": execution_id,
            }
        )

        cached_result = self._get_recent_result(execution_id)
        if cached_result is not None:
            delivery = await self._deliver_result(execution_id, cached_result)
            logger.warning(
                "Duplicate dispatch for %s after prior completion; "
                "skipping re-execution and re-delivering cached result "
                "(delivery=%s)",
                execution_id,
                delivery,
            )
            return

        # 2. Execute (guarded by _active_tasks to suppress pong timeout)
        self._active_tasks += 1
        start_time = time.monotonic()
        try:
            result = await self.task_handler(msg)
            duration = time.monotonic() - start_time

            # 3. Send result
            delivery = await self._deliver_result(
                execution_id,
                {
                    "type": "result",
                    "execution_id": execution_id,
                    "status": result.get("status", "completed"),
                    "output": result.get("output", ""),
                    "duration_seconds": duration,
                    "tool_calls": result.get("tool_calls", []),
                    "files_modified": result.get("files_modified", []),
                    "files_created": result.get("files_created", []),
                    "error": result.get("error"),
                    "metadata": {
                        "runtime_id": result.get("runtime_id"),
                    },
                    "governance": {
                        "output_hash": hashlib.sha256(
                            result.get("output", "").encode()
                        ).hexdigest(),
                        "summary": result.get("output", "")[:200],
                    },
                },
            )

            logger.info(
                f"Task completed: exec={execution_id}, "
                f"duration={duration:.1f}s, "
                f"status={result.get('status', 'completed')}, "
                f"delivery={delivery}"
            )

            # Auth failure = runtime is broken, disconnect so UI
            # shows unavailable instead of a false "connected".
            error_str = result.get("error", "") or ""
            if "Exit code 41" in error_str or "auth not set" in error_str.lower():
                logger.error(
                    "AUTH FAILURE detected (exit 41). "
                    "Disconnecting so status shows unavailable. "
                    "Restart with scripts/start_cli_bridge.sh "
                    f"--surface {self.surface} to fix."
                )
                await self.stop()

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(f"Task failed: {e}")
            await self._deliver_result(
                execution_id,
                {
                    "type": "result",
                    "execution_id": execution_id,
                    "status": "failed",
                    "output": "",
                    "duration_seconds": duration,
                    "error": str(e),
                },
            )
        finally:
            self._active_tasks = max(0, self._active_tasks - 1)

    async def _deliver_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> str:
        """Send result over WS and fall back to REST if the ACK never arrives."""
        self._remember_result(execution_id, result_message)
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[bool] = loop.create_future()
        self._result_ack_waiters[execution_id] = waiter

        try:
            await self._send(result_message)
        except Exception as exc:
            self._result_ack_waiters.pop(execution_id, None)
            logger.warning(
                "WS result send failed for %s: %s. Falling back to REST result submit.",
                execution_id,
                exc,
            )
            await self._submit_result_via_rest(result_message)
            return "rest_fallback_send_error"

        task = asyncio.create_task(
            self._wait_for_result_ack_or_fallback(
                execution_id,
                waiter,
                result_message,
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return "ws_push"

    async def _wait_for_result_ack_or_fallback(
        self,
        execution_id: str,
        waiter: asyncio.Future[bool],
        result_message: Dict[str, Any],
    ) -> None:
        try:
            await asyncio.wait_for(waiter, timeout=self.RESULT_ACK_TIMEOUT)
        except asyncio.TimeoutError:
            self._result_ack_waiters.pop(execution_id, None)
            logger.warning(
                "No result_ack for %s within %.1fs. Falling back to REST result submit.",
                execution_id,
                self.RESULT_ACK_TIMEOUT,
            )
            await self._submit_result_via_rest(result_message)
        except Exception as exc:
            self._result_ack_waiters.pop(execution_id, None)
            logger.warning(
                "Result ACK wait failed for %s: %s. Falling back to REST result submit.",
                execution_id,
                exc,
            )
            await self._submit_result_via_rest(result_message)
        else:
            self._result_ack_waiters.pop(execution_id, None)

    @property
    def backend_api_url(self) -> str:
        backend_url = os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip()
        if backend_url:
            return backend_url.rstrip("/")
        host = (self.host or "").strip()
        if host:
            if host.startswith("http://") or host.startswith("https://"):
                return host.rstrip("/")
            return f"http://{host}"
        return ""

    def _submit_result_via_rest_sync(self, result_message: Dict[str, Any]) -> Dict[str, Any]:
        backend_url = self.backend_api_url
        if not backend_url:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        payload = {
            "execution_id": result_message.get("execution_id", ""),
            "status": result_message.get("status", "completed"),
            "output": result_message.get("output", ""),
            "duration_seconds": result_message.get("duration_seconds", 0),
            "tool_calls": result_message.get("tool_calls", []),
            "files_modified": result_message.get("files_modified", []),
            "files_created": result_message.get("files_created", []),
            "error": result_message.get("error"),
            "governance": result_message.get("governance", {}),
            "metadata": {
                **(result_message.get("metadata") or {}),
                "transport": "rest_fallback",
                "client_id": self.client_id,
                "surface_type": self.surface,
            },
            "client_id": self.client_id,
        }
        req = urllib.request.Request(
            f"{backend_url}/api/v1/mcp/agent/result",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    async def _submit_result_via_rest(self, result_message: Dict[str, Any]) -> None:
        execution_id = result_message.get("execution_id", "")
        max_attempts = max(1, int(self.RESULT_REST_RETRY_ATTEMPTS))
        base_delay = max(0.1, float(self.RESULT_REST_RETRY_BASE_DELAY))

        for attempt in range(1, max_attempts + 1):
            try:
                response = await asyncio.to_thread(
                    self._submit_result_via_rest_sync,
                    result_message,
                )
                logger.info(
                    "REST result fallback accepted for %s: %s",
                    execution_id,
                    response.get("message", "accepted"),
                )
                return
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    logger.info(
                        "REST result fallback for %s returned 404; "
                        "backend likely already accepted or resolved the execution.",
                        execution_id,
                    )
                    return
                if exc.code >= 500 and attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "REST result fallback for %s failed with HTTP %s "
                        "(attempt %d/%d); retrying in %.1fs",
                        execution_id,
                        exc.code,
                        attempt,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    "REST result fallback failed for %s: HTTP %s",
                    execution_id,
                    exc.code,
                )
                return
            except (urllib.error.URLError, OSError, json.JSONDecodeError, RuntimeError) as exc:
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "REST result fallback transient failure for %s "
                        "(attempt %d/%d): %s. Retrying in %.1fs",
                        execution_id,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    "REST result fallback failed for %s after %d attempts: %s",
                    execution_id,
                    max_attempts,
                    exc,
                )
                return

    def _prune_recent_results(self) -> None:
        now = time.monotonic()
        while self._recent_results:
            execution_id, (stored_at, _result) = next(
                iter(self._recent_results.items())
            )
            if (
                len(self._recent_results) > self.RECENT_RESULT_MAX_SIZE
                or now - stored_at > self.RECENT_RESULT_TTL
            ):
                self._recent_results.pop(execution_id, None)
                continue
            break

    def _remember_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> None:
        self._recent_results[execution_id] = (
            time.monotonic(),
            copy.deepcopy(result_message),
        )
        self._recent_results.move_to_end(execution_id)
        self._prune_recent_results()

    def _get_recent_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        self._prune_recent_results()
        cached = self._recent_results.get(execution_id)
        if not cached:
            return None
        _stored_at, result_message = cached
        self._recent_results.move_to_end(execution_id)
        return copy.deepcopy(result_message)

    # ============================================================
    #  Send helpers
    # ============================================================

    async def _send(self, msg: Dict[str, Any]) -> None:
        """Send a JSON message over WebSocket."""
        if self._ws:
            await self._ws.send(json.dumps(msg))

    # ============================================================
    #  Default task handler
    # ============================================================

    async def _default_task_handler(
        self,
        dispatch_msg: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Default task handler -- logs the task and returns a stub result.

        Replace this with actual CLI runtime invocation in production.
        """
        task = dispatch_msg.get("task", "")
        execution_id = dispatch_msg.get("execution_id", "")

        logger.info(f"[DefaultHandler] Executing: {task[:100]}")

        # Send progress updates
        for pct in [25, 50, 75]:
            await asyncio.sleep(0.5)
            await self._send(
                {
                    "type": "progress",
                    "execution_id": execution_id,
                    "progress": {
                        "percent": pct,
                        "message": f"Processing... {pct}%",
                    },
                }
            )

        return {
            "status": "completed",
            "output": f"Default handler completed task: {task[:100]}",
            "tool_calls": [],
            "files_modified": [],
            "files_created": [],
        }


# ============================================================
#  CLI entry point
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Host-side WebSocket client for shared CLI surfaces"
    )
    parser.add_argument(
        "--workspace-id",
        default=os.environ.get("MINDSCAPE_WORKSPACE_ID", ""),
        required=not bool(os.environ.get("MINDSCAPE_WORKSPACE_ID")),
        help="Workspace ID",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MINDSCAPE_WS_HOST"),
        help="Backend host:port (auto-resolved from port config if omitted)",
    )
    parser.add_argument(
        "--auth-secret",
        default=os.environ.get("MINDSCAPE_AUTH_SECRET"),
        help="HMAC auth secret (optional)",
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="Client ID (auto-generated if not provided)",
    )
    parser.add_argument(
        "--surface",
        default="gemini_cli",
        help="Surface type (default: gemini_cli)",
    )
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("MINDSCAPE_WORKSPACE_ROOT", os.getcwd()),
        help="Workspace root directory for task execution",
    )
    args = parser.parse_args()

    # Auto-resolve host from PortConfigService if not provided
    if not args.host:
        try:
            from backend.app.services.port_config_service import port_config_service

            url = port_config_service.get_service_url("backend_api")
            # url = "http://host:port" -> extract "host:port"
            args.host = url.split("://", 1)[-1]
            logger.info(f"Host resolved from port config: {args.host}")
        except Exception:
            # DB unavailable -- use centralized default port constant
            try:
                from backend.app.services.port_config_service import PortConfigService

                port = PortConfigService.DEFAULT_PORTS["backend_api"]
                args.host = f"localhost:{port}"
            except Exception:
                args.host = "localhost:8200"
            logger.warning(f"Port config DB unavailable, using default: {args.host}")

    # Auto-derive env vars from CLI args so this works without a wrapper script.
    if not os.environ.get("MINDSCAPE_BACKEND_API_URL"):
        os.environ["MINDSCAPE_BACKEND_API_URL"] = f"http://{args.host}"
    if not os.environ.get("MINDSCAPE_WS_HOST"):
        os.environ["MINDSCAPE_WS_HOST"] = args.host
    # Auth mode is resolved dynamically by the bridge via /api/v1/auth/cli-token.
    # Do NOT force any auth mode here; the backend endpoint handles it.

    # Auto-discover the Gemini runtime bridge only when running the
    # gemini_cli surface. Codex and Claude do not use this bridge path.
    if args.surface == "gemini_cli" and not os.environ.get("GEMINI_CLI_RUNTIME_CMD"):
        # Walk up from this file to find project root containing the bridge
        _dir = os.path.dirname(os.path.abspath(__file__))
        for _ in range(10):
            bridge_path = os.path.join(_dir, "scripts", "gemini_cli_runtime_bridge.py")
            if os.path.isfile(bridge_path):
                # Use sys.executable for cross-platform compat (python3 doesn't exist on Windows)
                os.environ["GEMINI_CLI_RUNTIME_CMD"] = f"{sys.executable} {bridge_path}"
                break
            parent = os.path.dirname(_dir)
            if parent == _dir:
                break
            _dir = parent

    # Use the real TaskExecutor instead of the default stub handler.
    from backend.app.services.external_agents.bridge.task_executor import (
        HostBridgeTaskExecutor,
    )

    executor = HostBridgeTaskExecutor(
        workspace_root=args.workspace_root,
        runtime_surface=args.surface,
    )

    client = HostBridgeWSClient(
        workspace_id=args.workspace_id,
        host=args.host,
        auth_secret=args.auth_secret,
        client_id=args.client_id,
        surface=args.surface,
        task_handler=executor,
    )

    # Handle graceful shutdown
    loop = asyncio.new_event_loop()

    def shutdown(sig):
        logger.info(f"Received {sig.name}, shutting down...")
        loop.create_task(client.stop())

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: shutdown(s))
    except NotImplementedError:
        # Windows: add_signal_handler is not supported, use signal.signal fallback
        signal.signal(signal.SIGINT, lambda s, f: shutdown(signal.SIGINT))

    try:
        loop.run_until_complete(client.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
