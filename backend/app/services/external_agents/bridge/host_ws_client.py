"""
Host-side WebSocket client for shared CLI surfaces.

This script runs in the host environment to:
  1. Connect to the Mindscape backend via WebSocket
  2. Authenticate using HMAC challenge-response
  3. Receive dispatched coding tasks
  4. Execute tasks via the surface-specific CLI runtime
  5. Send back ack, progress, and result messages

Usage:
    python host_ws_client.py --workspace-id ws-123 --surface codex_cli
    python host_ws_client.py --workspace-id ws-123 --auth-secret my_secret

Environment Variables:
    MINDSCAPE_WS_HOST       Backend host (default: localhost:8000)
    MINDSCAPE_AUTH_SECRET    HMAC auth secret (optional, skipped in dev mode)
    MINDSCAPE_WORKSPACE_ID  Workspace ID
    MINDSCAPE_SURFACE       Required surface type
    MINDSCAPE_RESULT_ACK_TIMEOUT  Ack wait timeout before REST fallback
    MINDSCAPE_WS_OPEN_TIMEOUT  WebSocket opening handshake timeout
    MINDSCAPE_WS_PONG_TIMEOUT  App-level pong timeout before stale reconnect
"""

import argparse
import asyncio
import base64
import copy
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone
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

UNKNOWN_EXECUTION_ERROR_RE = re.compile(r"Unknown execution ([0-9a-fA-F-]+)")


def _env_float(name: str, default: float, *, minimum: Optional[float] = None) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %.1f", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning(
            "Invalid %s=%.3f below minimum %.3f; falling back to %.1f",
            name,
            value,
            minimum,
            default,
        )
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %s", name, raw, default)
        return default


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid %s=%r; falling back to %s", name, raw, default)
    return default


def _safe_path_component(value: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
        for ch in (value or "").strip()
    )
    return cleaned or "unknown"


def _runtime_identity() -> Dict[str, Any]:
    """Collect lightweight host-process identity for signal/debug traces."""
    identity: Dict[str, Any] = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "pgid": None,
        "xpc_service_name": os.environ.get("XPC_SERVICE_NAME", ""),
        "workspace_id": os.environ.get("MINDSCAPE_WORKSPACE_ID", ""),
        "surface": os.environ.get("MINDSCAPE_SURFACE", ""),
    }
    try:
        identity["pgid"] = os.getpgid(0)
    except OSError:
        identity["pgid"] = None
    return identity


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
    # Result ACKs can lag behind task completion when the backend is
    # under meeting load; keep the WS path alive long enough to avoid
    # unnecessary REST fallback churn on healthy-but-slow deliveries.
    RESULT_ACK_TIMEOUT: float = 15.0
    # Opening handshake can stall under heavy backend load; allow a
    # longer window than the websockets default so reconnects do not
    # flap during active long-running meetings.
    WS_OPEN_TIMEOUT: float = 30.0
    RESULT_REST_RETRY_ATTEMPTS: int = 4
    RESULT_REST_RETRY_BASE_DELAY: float = 1.0
    HOST_SESSION_REGISTER_TIMEOUT: float = 30.0
    HOST_SESSION_REGISTER_RETRY_INTERVAL: float = 15.0
    HOST_SESSION_REGISTER_REFRESH_INTERVAL: float = 300.0
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
        surface: Optional[str] = None,
        task_handler: Optional[Callable] = None,
    ):
        normalized_surface = (surface or "").strip()
        if not normalized_surface:
            raise ValueError("surface is required for HostBridgeWSClient")

        self.workspace_id = workspace_id
        self.host = host
        self.auth_secret = auth_secret
        self.client_id = client_id or str(uuid.uuid4())
        self.surface = normalized_surface
        self.task_handler = task_handler or self._default_task_handler
        self.owner_user_id = os.environ.get("MINDSCAPE_OWNER_USER_ID", "").strip()

        self._ws = None
        self._running = False
        self._reconnect_attempt = 0
        self._pong_received = asyncio.Event()
        self._active_tasks = 0  # suppress pong-timeout during execution
        self.RESULT_ACK_TIMEOUT = _env_float(
            "MINDSCAPE_RESULT_ACK_TIMEOUT",
            self.RESULT_ACK_TIMEOUT,
            minimum=0.1,
        )
        self.WS_OPEN_TIMEOUT = _env_float(
            "MINDSCAPE_WS_OPEN_TIMEOUT",
            self.WS_OPEN_TIMEOUT,
            minimum=1.0,
        )
        self.PONG_TIMEOUT = _env_float(
            "MINDSCAPE_WS_PONG_TIMEOUT",
            self.PONG_TIMEOUT,
            minimum=1.0,
        )
        self.HOST_SESSION_REGISTER_TIMEOUT = _env_float(
            "MINDSCAPE_CODEX_POOL_REGISTER_TIMEOUT",
            self.HOST_SESSION_REGISTER_TIMEOUT,
            minimum=1.0,
        )
        self.HOST_SESSION_REGISTER_RETRY_INTERVAL = _env_float(
            "MINDSCAPE_CODEX_POOL_REGISTER_RETRY_INTERVAL",
            self.HOST_SESSION_REGISTER_RETRY_INTERVAL,
            minimum=1.0,
        )
        self.HOST_SESSION_REGISTER_REFRESH_INTERVAL = _env_float(
            "MINDSCAPE_CODEX_POOL_REGISTER_REFRESH_INTERVAL",
            self.HOST_SESSION_REGISTER_REFRESH_INTERVAL,
            minimum=5.0,
        )
        self._result_ack_waiters: Dict[str, asyncio.Future[bool]] = {}
        self._background_tasks: Set[asyncio.Task] = set()
        self._recent_results: (
            "OrderedDict[str, tuple[float, float, Dict[str, Any]]]"
        ) = OrderedDict()
        self._pending_rest_results: "OrderedDict[str, Dict[str, Any]]" = (
            OrderedDict()
        )
        self._pending_rest_flush_task: Optional[asyncio.Task] = None
        self._result_spool_path = self._resolve_result_spool_path()
        self._codex_seed_registry_path = self._resolve_codex_seed_registry_path()
        self._codex_managed_pool_root = self._resolve_codex_managed_pool_root()
        self._codex_managed_pool_size = max(
            0,
            _env_int("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", 3),
        )
        self._load_result_spool()
        self._host_session_runtime_registered = False
        self._host_session_runtime_last_attempt_fingerprint: Optional[str] = None
        self._host_session_runtime_last_registered_fingerprint: Optional[str] = None
        self._host_session_runtime_next_attempt_at: float = 0.0
        self._host_session_runtime_last_success_at: float = 0.0
        self._host_session_runtime_registration_failure_count: int = 0

    @property
    def ws_url(self) -> str:
        """Build WebSocket URL."""
        return (
            f"ws://{self.host}/ws/agent/{self.workspace_id}"
            f"?client_id={self.client_id}&surface={self.surface}"
        )

    def _has_pending_transport_work(self) -> bool:
        """Whether the bridge should tolerate temporary WS silence."""
        if self._active_tasks > 0:
            return True
        return any(not waiter.done() for waiter in self._result_ack_waiters.values())

    def _pending_result_ack_count(self) -> int:
        return sum(1 for waiter in self._result_ack_waiters.values() if not waiter.done())

    def _resolve_result_spool_path(self) -> Path:
        override = os.environ.get("MINDSCAPE_RESULT_SPOOL_PATH", "").strip()
        if override:
            path = Path(os.path.expanduser(override))
            if path.suffix:
                return path
            return path / f"{_safe_path_component(self.client_id)}.json"

        return (
            Path(tempfile.gettempdir())
            / "mindscape-bridge-results"
            / _safe_path_component(self.workspace_id)
            / _safe_path_component(self.surface)
            / f"{_safe_path_component(self.client_id)}.json"
        )

    def _load_result_spool(self) -> None:
        path = self._result_spool_path
        if not path.exists():
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load result spool %s: %s", path, exc)
            return

        now_wall = time.time()
        now_monotonic = time.monotonic()

        pending_entries = payload.get("pending_rest_results") or []
        if isinstance(pending_entries, dict):
            pending_entries = [
                {
                    "execution_id": execution_id,
                    "result_message": result_message,
                }
                for execution_id, result_message in pending_entries.items()
            ]
        for entry in pending_entries:
            execution_id = str(entry.get("execution_id", "")).strip()
            result_message = entry.get("result_message")
            if not execution_id or not isinstance(result_message, dict):
                continue
            self._pending_rest_results[execution_id] = copy.deepcopy(result_message)

        recent_entries = payload.get("recent_results") or []
        if isinstance(recent_entries, dict):
            recent_entries = [
                {
                    "execution_id": execution_id,
                    "stored_at": entry.get("stored_at"),
                    "result_message": entry.get("result_message"),
                }
                for execution_id, entry in recent_entries.items()
                if isinstance(entry, dict)
            ]
        for entry in recent_entries:
            execution_id = str(entry.get("execution_id", "")).strip()
            result_message = entry.get("result_message")
            stored_at_wall = entry.get("stored_at")
            if not execution_id or not isinstance(result_message, dict):
                continue
            try:
                stored_at_wall_value = float(stored_at_wall)
            except (TypeError, ValueError):
                stored_at_wall_value = now_wall
            age_seconds = max(0.0, now_wall - stored_at_wall_value)
            if age_seconds > self.RECENT_RESULT_TTL:
                continue
            stored_at_monotonic = now_monotonic - age_seconds
            self._recent_results[execution_id] = (
                stored_at_monotonic,
                stored_at_wall_value,
                copy.deepcopy(result_message),
            )

        self._prune_recent_results()
        if self._pending_rest_results or self._recent_results:
            logger.info(
                "Loaded result spool %s (pending=%d recent=%d)",
                path,
                len(self._pending_rest_results),
                len(self._recent_results),
            )

    def _persist_result_spool(self) -> None:
        path = self._result_spool_path

        if not self._pending_rest_results and not self._recent_results:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning("Failed to remove empty result spool %s: %s", path, exc)
            return

        payload = {
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "surface": self.surface,
            "updated_at": time.time(),
            "pending_rest_results": [
                {
                    "execution_id": execution_id,
                    "result_message": copy.deepcopy(result_message),
                }
                for execution_id, result_message in self._pending_rest_results.items()
            ],
            "recent_results": [
                {
                    "execution_id": execution_id,
                    "stored_at": stored_at_wall,
                    "result_message": copy.deepcopy(result_message),
                }
                for execution_id, (_stored_at_monotonic, stored_at_wall, result_message) in self._recent_results.items()
            ],
        }

        tmp_path = path.with_suffix(f"{path.suffix or '.json'}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except Exception as exc:
            logger.warning("Failed to persist result spool %s: %s", path, exc)
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass

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
                    "Start this client via "
                    "scripts/start_cli_bridge_supervisor.sh "
                    "--surfaces gemini_cli --all, which sets the required "
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

    def _start_background_task(
        self,
        coro: Coroutine[Any, Any, Any],
    ) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def run(self) -> None:
        """Main entry point -- connect with auto-reconnect."""
        self._preflight_check()
        self._running = True
        runtime_identity = _runtime_identity()
        logger.info(
            (
                "Starting host bridge WS client "
                "(workspace=%s surface=%s pid=%s ppid=%s pgid=%s xpc_service=%s)"
            ),
            self.workspace_id,
            self.surface,
            runtime_identity.get("pid"),
            runtime_identity.get("ppid"),
            runtime_identity.get("pgid"),
            runtime_identity.get("xpc_service_name") or "-",
        )

        if self._should_auto_register_host_session_runtime():
            self._start_background_task(
                self._ensure_host_session_runtime_registered_loop()
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
        pending_background = list(self._background_tasks)
        for task in pending_background:
            task.cancel()
        if pending_background:
            await asyncio.gather(*pending_background, return_exceptions=True)
        logger.info("Host bridge WS client stopped")

    async def _ensure_host_session_runtime_registered_loop(self) -> None:
        while self._running:
            await self._maybe_register_host_session_runtime()
            if not self._running:
                return
            await asyncio.sleep(self.HOST_SESSION_REGISTER_RETRY_INTERVAL)

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
            open_timeout=self.WS_OPEN_TIMEOUT,
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
                    pending_result_acks = self._pending_result_ack_count()
                    if self._has_pending_transport_work():
                        if self._active_tasks == 0 and pending_result_acks > 0:
                            logger.warning(
                                "Pong timeout while awaiting %s result_ack(s) "
                                "with no active task — forcing REST recovery and reconnect",
                                pending_result_acks,
                            )
                            await self._recover_pending_result_acks_due_to_stale_connection()
                            await self._ws.close()
                            break
                        logger.info(
                            "Pong timeout but transport work is still pending "
                            "(active_tasks=%s pending_result_acks=%s) — "
                            "keeping connection alive",
                            self._active_tasks,
                            pending_result_acks,
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
            self._schedule_pending_result_flush()
            await self._send_resume_state()
        elif msg_type == "auth_ok":
            logger.info(f"Authenticated! flushed={msg.get('flushed_tasks', 0)} tasks")
            self._schedule_pending_result_flush()
            await self._send_resume_state()
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
            self._pending_rest_results.pop(execution_id, None)
            self._persist_result_spool()
            logger.debug(f"Result acknowledged: {msg.get('execution_id')}")
        elif msg_type == "resume_sync":
            self._handle_resume_sync(msg)
        elif msg_type == "error":
            error_message = str(msg.get("error") or "")
            logger.error(f"Server error: {error_message}")
            self._start_background_task(
                self._recover_unknown_execution_via_rest(error_message)
            )
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

    def _build_resume_state_message(self) -> Dict[str, Any]:
        self._prune_recent_results()
        last_completed_at = 0.0
        for _execution_id, (_stored_at_monotonic, stored_at_wall, _result) in (
            self._recent_results.items()
        ):
            last_completed_at = max(last_completed_at, float(stored_at_wall or 0.0))
        return {
            "type": "resume_state",
            "recent_execution_ids": list(self._recent_results.keys()),
            "pending_rest_execution_ids": list(self._pending_rest_results.keys()),
            "last_completed_at": last_completed_at,
        }

    async def _send_resume_state(self) -> None:
        await self._send(self._build_resume_state_message())

    def _handle_resume_sync(self, msg: Dict[str, Any]) -> None:
        replayed = msg.get("replayed_completions") or []
        duplicates = msg.get("duplicates_to_ignore") or []
        reconciled: set[str] = set()

        for entry in replayed:
            if not isinstance(entry, dict):
                continue
            execution_id = str(entry.get("execution_id") or "").strip()
            if execution_id:
                reconciled.add(execution_id)

        for raw_execution_id in duplicates:
            execution_id = str(raw_execution_id or "").strip()
            if execution_id:
                reconciled.add(execution_id)

        if not reconciled:
            logger.info(
                "Resume sync received: replay=%d dup=%d requeue=%d",
                len(replayed),
                len(duplicates),
                len(msg.get("tasks_to_requeue") or []),
            )
            return

        for execution_id in reconciled:
            waiter = self._result_ack_waiters.pop(execution_id, None)
            if waiter and not waiter.done():
                waiter.set_result(True)
            self._pending_rest_results.pop(execution_id, None)

        self._persist_result_spool()
        logger.info(
            "Resume sync reconciled %d execution(s); replay=%d dup=%d requeue=%d",
            len(reconciled),
            len(replayed),
            len(duplicates),
            len(msg.get("tasks_to_requeue") or []),
        )

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
                    "attachments": result.get("attachments", []),
                    "files_modified": result.get("files_modified", []),
                    "files_created": result.get("files_created", []),
                    "error": result.get("error"),
                    "metadata": {
                        **(
                            result.get("metadata")
                            if isinstance(result.get("metadata"), dict)
                            else {}
                        ),
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
                    "Restart with scripts/start_cli_bridge_supervisor.sh "
                    f"--surfaces {self.surface} --all to fix."
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

        task = self._start_background_task(
            self._wait_for_result_ack_or_fallback(
                execution_id,
                waiter,
                result_message,
            )
        )
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

    async def _recover_pending_result_acks_due_to_stale_connection(self) -> None:
        pending_execution_ids = [
            execution_id
            for execution_id, waiter in self._result_ack_waiters.items()
            if not waiter.done()
        ]
        if not pending_execution_ids:
            return

        logger.warning(
            "Recovering %d pending result_ack(s) via REST fallback after stale connection: %s",
            len(pending_execution_ids),
            pending_execution_ids,
        )

        for execution_id in pending_execution_ids:
            waiter = self._result_ack_waiters.pop(execution_id, None)
            if waiter and not waiter.done():
                waiter.set_result(True)

            result_message = self._get_recent_result(execution_id)
            if result_message is None:
                logger.warning(
                    "Missing cached result for %s during stale-connection recovery",
                    execution_id,
                )
                continue
            await self._submit_result_via_rest(result_message)

    async def _recover_unknown_execution_via_rest(self, error_message: str) -> None:
        match = UNKNOWN_EXECUTION_ERROR_RE.search(str(error_message or ""))
        if not match:
            return
        execution_id = str(match.group(1) or "").strip()
        if not execution_id:
            return

        result_message = self._get_recent_result(execution_id)
        if result_message is None:
            return

        waiter = self._result_ack_waiters.pop(execution_id, None)
        if waiter and not waiter.done():
            waiter.set_result(True)

        logger.warning(
            "Server rejected WS result for %s as unknown execution; attempting immediate REST recovery",
            execution_id,
        )
        await self._submit_result_via_rest(result_message)

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

    def _should_auto_register_host_session_runtime(self) -> bool:
        if self.surface != "codex_cli":
            return False
        if _env_flag("MINDSCAPE_CODEX_POOL_AUTO_REGISTER", True):
            return True
        return _env_flag("MINDSCAPE_CLI_RUNTIME_AUTO_REGISTER", False)

    def _resolve_codex_seed_registry_path(self) -> Path:
        override = os.environ.get("MINDSCAPE_CODEX_HOME_SEED_REGISTRY", "").strip()
        if override:
            return Path(os.path.expanduser(override))
        return Path.home() / ".mindscape" / "codex_host_session_seeds.json"

    def _resolve_codex_managed_pool_root(self) -> Path:
        override = os.environ.get("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", "").strip()
        if override:
            return Path(os.path.expanduser(override))
        return Path.home() / ".mindscape" / "runtime" / "codex-home-pool"

    def _load_codex_seed_registry(self) -> Dict[str, Dict[str, Any]]:
        path = self._codex_seed_registry_path
        if not path.exists():
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load Codex seed registry %s: %s", path, exc)
            return {}

        entries = payload.get("homes")
        if not isinstance(entries, list):
            return {}

        registry: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                continue
            normalized = str(Path(os.path.expanduser(raw_path)))
            registry[normalized] = {
                "sources": self._normalize_seed_sources(item.get("sources")),
                "last_seen_at": str(item.get("last_seen_at") or "").strip(),
                "account_key": str(item.get("account_key") or "").strip(),
            }
        return registry

    def _write_codex_seed_registry(self, entries: Dict[str, Dict[str, Any]]) -> None:
        path = self._codex_seed_registry_path
        if not entries:
            return

        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "homes": [
                {
                    "path": codex_home,
                    "sources": sorted(meta.get("sources") or []),
                    "last_seen_at": meta.get("last_seen_at"),
                    "account_key": str(meta.get("account_key") or "").strip() or None,
                }
                for codex_home, meta in sorted(entries.items())
            ],
        }

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist Codex seed registry %s: %s", path, exc)

    @staticmethod
    def _normalize_seed_sources(raw_sources: Any) -> set[str]:
        sources: set[str] = set()
        if isinstance(raw_sources, (list, tuple, set)):
            for item in raw_sources:
                value = str(item or "").strip().lower()
                if value:
                    sources.add(value)
            return sources
        value = str(raw_sources or "").strip().lower()
        if value:
            sources.add(value)
        return sources

    def _codex_home_has_login_trace(self, codex_home: str) -> bool:
        path = Path(codex_home)
        if not path.is_dir():
            return False

        auth_path = path / "auth.json"
        if not auth_path.is_file():
            return False

        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Ignoring unreadable Codex auth trace: %s", auth_path)
            return False

        if not isinstance(payload, dict):
            return False

        auth_mode = str(payload.get("auth_mode") or "").strip()
        tokens = payload.get("tokens")
        api_key = str(payload.get("OPENAI_API_KEY") or "").strip()
        return bool(auth_mode or api_key or isinstance(tokens, dict))

    @staticmethod
    def _load_codex_auth_payload(codex_home: str) -> Dict[str, Any]:
        auth_path = Path(os.path.expanduser(codex_home)) / "auth.json"
        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _decode_jwt_payload(token: str) -> Dict[str, Any]:
        raw = str(token or "").strip()
        if raw.count(".") < 2:
            return {}
        try:
            encoded = raw.split(".", 2)[1]
            encoded += "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
            payload = json.loads(decoded.decode("utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _extract_codex_account_key(self, codex_home: str) -> str:
        payload = self._load_codex_auth_payload(codex_home)
        if not payload:
            return ""

        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        id_token_payload = self._decode_jwt_payload(tokens.get("id_token"))
        auth_claims = (
            id_token_payload.get("https://api.openai.com/auth")
            if isinstance(id_token_payload.get("https://api.openai.com/auth"), dict)
            else {}
        )

        principal_candidates = (
            str(auth_claims.get("chatgpt_user_id") or "").strip(),
            str(auth_claims.get("user_id") or "").strip(),
            str(id_token_payload.get("sub") or "").strip(),
            str(id_token_payload.get("email") or "").strip().lower(),
        )
        for principal in principal_candidates:
            if principal:
                return hashlib.sha256(f"user:{principal}".encode("utf-8")).hexdigest()[:24]

        account_id = str(tokens.get("account_id") or "").strip()
        if account_id:
            return hashlib.sha256(f"account:{account_id}".encode("utf-8")).hexdigest()[:24]

        api_key = str(payload.get("OPENAI_API_KEY") or "").strip()
        if api_key:
            return hashlib.sha256(f"api_key:{api_key}".encode("utf-8")).hexdigest()[:24]

        refresh_token = str(tokens.get("refresh_token") or "").strip()
        if refresh_token:
            return hashlib.sha256(f"refresh:{refresh_token}".encode("utf-8")).hexdigest()[:24]

        return ""

    def _is_managed_codex_home(self, codex_home: str) -> bool:
        try:
            return Path(os.path.expanduser(codex_home)).resolve().is_relative_to(
                self._codex_managed_pool_root.resolve()
            )
        except Exception:
            return False

    @staticmethod
    def _read_codex_managed_seed_metadata(codex_home: str) -> Dict[str, Any]:
        metadata_path = Path(os.path.expanduser(codex_home)) / ".mindscape-seed.json"
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _codex_quota_scope_home(self, codex_home: str) -> str:
        normalized_home = str(Path(os.path.expanduser(codex_home)))
        if not self._is_managed_codex_home(normalized_home):
            return normalized_home

        metadata = self._read_codex_managed_seed_metadata(normalized_home)
        if not metadata.get("managed_mirror"):
            return normalized_home
        source_home = str(metadata.get("source_home") or "").strip()
        if source_home:
            return str(Path(os.path.expanduser(source_home)))
        return normalized_home

    def _codex_quota_scope_key(self, codex_home: str) -> str:
        quota_scope_home = self._codex_quota_scope_home(codex_home)
        return hashlib.sha1(quota_scope_home.encode("utf-8")).hexdigest()[:16]

    def _codex_managed_seed_copy_specs(self) -> tuple[tuple[str, str], ...]:
        return (
            ("auth.json", "auth.json"),
            ("config.toml", "config.toml"),
            ("installation_id", "installation_id"),
            ("AGENTS.md", "AGENTS.md"),
            (".personality_migration", ".personality_migration"),
            ("rules/default.rules", "rules/default.rules"),
        )

    def _sync_codex_home_mirror(self, source_home: str, target_home: Path, *, slot: int) -> bool:
        source_path = Path(os.path.expanduser(source_home))
        if not self._codex_home_has_login_trace(str(source_path)):
            return False

        try:
            target_home.mkdir(parents=True, exist_ok=True)
            for relative_src, relative_dst in self._codex_managed_seed_copy_specs():
                src_path = source_path / relative_src
                if not src_path.exists():
                    continue
                dst_path = target_home / relative_dst
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)

            metadata_path = target_home / ".mindscape-seed.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "managed_mirror": True,
                        "slot": slot,
                        "source_home": str(source_path),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to materialize managed Codex home mirror %s from %s: %s",
                target_home,
                source_path,
                exc,
            )
            return False

    def _sync_codex_account_snapshot(
        self,
        source_home: str,
        target_home: Path,
        *,
        account_key: str,
    ) -> bool:
        source_path = Path(os.path.expanduser(source_home))
        if not self._codex_home_has_login_trace(str(source_path)):
            return False
        if not account_key:
            return False

        try:
            target_home.mkdir(parents=True, exist_ok=True)
            for relative_src, relative_dst in self._codex_managed_seed_copy_specs():
                src_path = source_path / relative_src
                if not src_path.exists():
                    continue
                dst_path = target_home / relative_dst
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)

            metadata_path = target_home / ".mindscape-seed.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "account_snapshot": True,
                        "account_key": account_key,
                        "source_home": str(source_path),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to materialize Codex account snapshot %s from %s: %s",
                target_home,
                source_path,
                exc,
            )
            return False

    def _materialize_managed_codex_home_mirrors(
        self,
        entries: Dict[str, set[str]],
    ) -> Dict[str, set[str]]:
        if self.surface != "codex_cli":
            return {}
        if self._codex_managed_pool_size <= 1:
            return {}

        real_homes = [
            path
            for path in entries.keys()
            if not self._is_managed_codex_home(path)
        ]
        if len(real_homes) != 1:
            return {}

        target_total = max(self._codex_managed_pool_size, len(real_homes))
        missing_count = max(0, target_total - len(entries))
        if missing_count == 0:
            return {}

        primary_home = real_homes[0]
        source_tag = f"{_safe_path_component(Path(primary_home).name)}-{hashlib.sha1(primary_home.encode('utf-8')).hexdigest()[:10]}"
        base_dir = self._codex_managed_pool_root / source_tag

        mirrors: Dict[str, set[str]] = {}
        for slot in range(1, missing_count + 1):
            target_home = base_dir / f"mirror-{slot:02d}"
            if not self._sync_codex_home_mirror(primary_home, target_home, slot=slot):
                continue
            mirrors[str(target_home)] = {"managed_mirror", "registration"}
        return mirrors

    def _discover_codex_home_candidates(self) -> Dict[str, set[str]]:
        discovered: Dict[str, set[str]] = {}
        if self.surface != "codex_cli":
            return discovered

        home_dir = Path(os.path.expanduser(os.environ.get("HOME", "").strip() or str(Path.home())))
        candidate_paths: list[tuple[str, str]] = []
        for pattern in (".codex*", "codex*"):
            for candidate in home_dir.glob(pattern):
                candidate_paths.append((str(candidate), "home_glob"))

        registry_entries = self._load_codex_seed_registry()
        for candidate_path in registry_entries.keys():
            candidate_paths.append((candidate_path, "seed_registry"))

        seen: set[str] = set()
        for raw_path, source in candidate_paths:
            normalized = str(Path(os.path.expanduser(raw_path)))
            if normalized in seen:
                continue
            seen.add(normalized)
            if not self._codex_home_has_login_trace(normalized):
                continue
            discovered.setdefault(normalized, set()).add(source)
        return discovered

    def _remember_codex_home_seeds(self, entries: Dict[str, set[str]]) -> None:
        registry = self._load_codex_seed_registry()
        now_iso = datetime.now(timezone.utc).isoformat()
        changed = False
        for codex_home, sources in entries.items():
            normalized = str(Path(os.path.expanduser(codex_home)))
            existing = registry.get(normalized, {"sources": set(), "last_seen_at": ""})
            merged_sources = set(existing.get("sources") or set()) | set(sources)
            if self._codex_home_has_login_trace(normalized):
                last_seen_at = now_iso
                account_key = self._extract_codex_account_key(normalized)
            else:
                last_seen_at = existing.get("last_seen_at", "")
                account_key = str(existing.get("account_key") or "").strip()
            next_meta = {
                "sources": merged_sources,
                "last_seen_at": last_seen_at,
                "account_key": account_key,
            }
            if registry.get(normalized) != next_meta:
                registry[normalized] = next_meta
                changed = True

        if changed:
            self._write_codex_seed_registry(registry)

    def _codex_seed_registry_summary(self) -> Dict[str, Any]:
        registry = self._load_codex_seed_registry()
        distinct_account_keys = sorted(
            {
                str(meta.get("account_key") or "").strip()
                for meta in registry.values()
                if str(meta.get("account_key") or "").strip()
            }
        )
        real_home_count = 0
        managed_mirror_count = 0
        account_snapshot_count = 0
        for codex_home in registry.keys():
            metadata = self._read_codex_managed_seed_metadata(codex_home)
            if metadata.get("account_snapshot"):
                account_snapshot_count += 1
            elif metadata.get("managed_mirror"):
                managed_mirror_count += 1
            else:
                real_home_count += 1
        return {
            "registry_home_count": len(registry),
            "distinct_account_count": len(distinct_account_keys),
            "distinct_account_keys": distinct_account_keys,
            "real_home_count": real_home_count,
            "managed_mirror_count": managed_mirror_count,
            "account_snapshot_count": account_snapshot_count,
        }

    def refresh_codex_home_seeds(self) -> Dict[str, Any]:
        if self.surface != "codex_cli":
            return {
                "surface": self.surface,
                "refreshed": False,
                "reason": "unsupported_surface",
            }

        active_pool_homes = self._codex_home_pool_entries()
        summary = self._codex_seed_registry_summary()
        summary.update(
            {
                "surface": self.surface,
                "refreshed": True,
                "active_pool_home_count": len(active_pool_homes),
            }
        )
        logger.info(
            (
                "Codex seed refresh complete: registry_homes=%s "
                "distinct_accounts=%s real_homes=%s snapshots=%s mirrors=%s "
                "active_pool_homes=%s"
            ),
            summary["registry_home_count"],
            summary["distinct_account_count"],
            summary["real_home_count"],
            summary["account_snapshot_count"],
            summary["managed_mirror_count"],
            summary["active_pool_home_count"],
        )
        return summary

    def _build_host_session_runtime_registration_payload(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key in (
            "CODEX_HOME",
            "HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        ):
            value = os.environ.get(key, "").strip()
            if value:
                metadata[key] = value

        if "CODEX_HOME" not in metadata:
            home_dir = metadata.get("HOME") or str(Path.home())
            default_codex_home = Path(home_dir) / ".codex"
            if default_codex_home.exists():
                metadata["CODEX_HOME"] = str(default_codex_home)

        codex_home = metadata.get("CODEX_HOME") or metadata.get("HOME") or self.client_id
        runtime_name = os.environ.get("MINDSCAPE_CODEX_RUNTIME_NAME", "").strip()
        if not runtime_name:
            runtime_name = f"codex_cli host session ({Path(codex_home).name})"

        runtime_id = os.environ.get("MINDSCAPE_CODEX_RUNTIME_ID", "").strip() or None
        pool_group = os.environ.get("MINDSCAPE_CODEX_POOL_GROUP", "").strip() or "codex-cli-pool"
        pool_priority = _env_int("MINDSCAPE_CODEX_POOL_PRIORITY", 0)
        pool_enabled = _env_flag("MINDSCAPE_CODEX_POOL_ENABLED", True)
        if self.surface == "codex_cli" and isinstance(codex_home, str) and codex_home.strip():
            quota_scope_home = self._codex_quota_scope_home(codex_home)
            metadata["quota_scope_home"] = quota_scope_home
            metadata["quota_scope_key"] = self._codex_quota_scope_key(codex_home)
            if quota_scope_home != codex_home:
                metadata["managed_seed_source_home"] = quota_scope_home

        payload = {
            "workspace_id": self.workspace_id,
            "surface": self.surface,
            "client_id": self.client_id,
            "runtime_id": runtime_id,
            "runtime_name": runtime_name,
            "pool_group": pool_group,
            "pool_enabled": pool_enabled,
            "pool_priority": pool_priority,
            "metadata": metadata,
        }
        if self.owner_user_id:
            payload["owner_user_id"] = self.owner_user_id
        return payload

    def _codex_home_pool_entries(self) -> list[str]:
        entries: Dict[str, set[str]] = {}
        raw = os.environ.get("MINDSCAPE_CODEX_HOME_POOL", "").strip()
        if raw:
            parts = [
                part.strip()
                for part in re.split(r"[\n,;{}]+".format(re.escape(os.pathsep)), raw)
                if part.strip()
            ]
            for part in parts:
                path = str(Path(os.path.expanduser(part))).strip()
                if not path:
                    continue
                if not Path(path).exists():
                    logger.warning("Ignoring missing CODEX_HOME pool path: %s", path)
                    continue
                entries.setdefault(path, set()).add("env_pool")

        if _env_flag("MINDSCAPE_CODEX_HOME_AUTO_DISCOVER", True):
            for path, sources in self._discover_codex_home_candidates().items():
                entries.setdefault(path, set()).update(sources)

        primary_codex_home = os.environ.get("CODEX_HOME", "").strip()
        if not primary_codex_home:
            default_codex_home = Path(
                os.path.expanduser(os.environ.get("HOME", "").strip() or str(Path.home()))
            ) / ".codex"
            if default_codex_home.exists():
                primary_codex_home = str(default_codex_home)

        account_snapshots = self._materialize_codex_account_snapshots(
            entries,
            primary_codex_home=primary_codex_home,
        )
        if account_snapshots:
            snapshot_registry_entries = {
                **entries,
                **{path: set(sources) for path, sources in account_snapshots.items()},
            }
            self._remember_codex_home_seeds(snapshot_registry_entries)
        for path, sources in account_snapshots.items():
            entries.setdefault(path, set()).update(sources)

        entries = self._prune_duplicate_account_snapshots(entries)
        for path, sources in self._materialize_managed_codex_home_mirrors(entries).items():
            entries.setdefault(path, set()).update(sources)
        self._remember_codex_home_seeds(entries)
        return list(entries.keys())

    def _materialize_codex_account_snapshots(
        self,
        entries: Dict[str, set[str]],
        *,
        primary_codex_home: str,
    ) -> Dict[str, set[str]]:
        if self.surface != "codex_cli":
            return {}
        normalized_primary = str(
            Path(os.path.expanduser(str(primary_codex_home or "").strip()))
        )
        if not normalized_primary or self._is_managed_codex_home(normalized_primary):
            return {}
        if not self._codex_home_has_login_trace(normalized_primary):
            return {}

        account_key = self._extract_codex_account_key(normalized_primary)
        if not account_key:
            return {}

        snapshot_home = (
            self._codex_managed_pool_root / "accounts" / f"acct-{account_key[:16]}"
        )
        if not self._sync_codex_account_snapshot(
            normalized_primary,
            snapshot_home,
            account_key=account_key,
        ):
            return {}
        return {str(snapshot_home): {"account_snapshot", "registration"}}

    def _prune_duplicate_account_snapshots(
        self,
        entries: Dict[str, set[str]],
    ) -> Dict[str, set[str]]:
        real_account_keys: set[str] = set()
        for codex_home in entries.keys():
            normalized = str(Path(os.path.expanduser(codex_home)))
            if self._is_managed_codex_home(normalized):
                continue
            account_key = self._extract_codex_account_key(normalized)
            if account_key:
                real_account_keys.add(account_key)

        if not real_account_keys:
            return entries

        filtered: Dict[str, set[str]] = {}
        for codex_home, sources in entries.items():
            normalized = str(Path(os.path.expanduser(codex_home)))
            metadata = self._read_codex_managed_seed_metadata(normalized)
            if metadata.get("account_snapshot"):
                account_key = str(metadata.get("account_key") or "").strip()
                if account_key and account_key in real_account_keys:
                    continue
            filtered[normalized] = set(sources)
        return filtered

    def _build_host_session_runtime_registration_payloads(self) -> list[Dict[str, Any]]:
        base_payload = self._build_host_session_runtime_registration_payload()
        base_priority = int(base_payload.get("pool_priority", 0))
        base_metadata = dict(base_payload.get("metadata") or {})
        home_value = str(base_metadata.get("HOME") or "").strip()
        primary_codex_home = str(base_metadata.get("CODEX_HOME") or "").strip()

        codex_homes = self._codex_home_pool_entries()
        if primary_codex_home and primary_codex_home not in codex_homes:
            codex_homes.insert(0, primary_codex_home)

        remembered_entries: Dict[str, set[str]] = {}
        for codex_home in codex_homes:
            remembered_entries.setdefault(codex_home, set()).add("registration")
        if primary_codex_home:
            remembered_entries.setdefault(primary_codex_home, set()).add("primary_runtime")
        self._remember_codex_home_seeds(remembered_entries)

        if not codex_homes:
            return [base_payload]

        payloads: list[Dict[str, Any]] = []
        for offset, codex_home in enumerate(codex_homes):
            payload = dict(base_payload)
            metadata = dict(base_metadata)
            metadata["CODEX_HOME"] = codex_home
            if home_value:
                metadata["HOME"] = home_value
            account_key = self._extract_codex_account_key(codex_home)
            if account_key:
                metadata["account_key"] = account_key
            quota_scope_home = self._codex_quota_scope_home(codex_home)
            metadata["quota_scope_home"] = quota_scope_home
            metadata["quota_scope_key"] = self._codex_quota_scope_key(codex_home)
            if quota_scope_home != codex_home:
                metadata["managed_seed_source_home"] = quota_scope_home
            metadata["seed_capture_managed"] = True
            metadata["seed_registry_path"] = str(self._codex_seed_registry_path)
            metadata["seed_last_seen_at"] = datetime.now(timezone.utc).isoformat()
            payload["metadata"] = metadata
            payload["pool_priority"] = base_priority + offset
            payload["runtime_name"] = f"codex_cli host session ({Path(codex_home).name})"
            payloads.append(payload)
        return payloads

    @staticmethod
    def _host_session_registration_fingerprint(
        payloads: list[Dict[str, Any]],
    ) -> str:
        normalized: list[Dict[str, Any]] = []
        for payload in payloads:
            item = copy.deepcopy(payload)
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                metadata.pop("seed_last_seen_at", None)
            normalized.append(item)
        serialized = json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha1(serialized.encode("utf-8")).hexdigest()

    def _host_session_registration_backoff_seconds(self) -> float:
        failures = max(0, self._host_session_runtime_registration_failure_count - 1)
        return min(
            self.HOST_SESSION_REGISTER_RETRY_INTERVAL * (2**failures),
            self.HOST_SESSION_REGISTER_REFRESH_INTERVAL,
        )

    def _register_host_session_runtime_sync(
        self,
        payloads: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        backend_url = self.backend_api_url
        if not backend_url:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        responses: list[Dict[str, Any]] = []
        for payload in payloads or self._build_host_session_runtime_registration_payloads():
            req = urllib.request.Request(
                f"{backend_url}/api/v1/auth/cli-runtime/register-host-session",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(
                req,
                timeout=self.HOST_SESSION_REGISTER_TIMEOUT,
            ) as response:
                body = response.read().decode("utf-8")
            responses.append(json.loads(body) if body else {})

        primary = responses[0] if responses else {}
        if len(responses) <= 1:
            return primary
        primary["registered_runtime_ids"] = [
            str(item.get("runtime_id") or "").strip()
            for item in responses
            if str(item.get("runtime_id") or "").strip()
        ]
        primary["registered_runtime_count"] = len(primary["registered_runtime_ids"])
        return primary

    async def _maybe_register_host_session_runtime(self) -> None:
        if not self._should_auto_register_host_session_runtime():
            return
        payloads = self._build_host_session_runtime_registration_payloads()
        fingerprint = self._host_session_registration_fingerprint(payloads)
        now = time.monotonic()
        if (
            self._host_session_runtime_registered
            and fingerprint == self._host_session_runtime_last_registered_fingerprint
            and now
            < (
                self._host_session_runtime_last_success_at
                + self.HOST_SESSION_REGISTER_REFRESH_INTERVAL
            )
        ):
            return
        if (
            fingerprint == self._host_session_runtime_last_attempt_fingerprint
            and now < self._host_session_runtime_next_attempt_at
        ):
            return
        self._host_session_runtime_last_attempt_fingerprint = fingerprint
        try:
            response = await asyncio.to_thread(
                self._register_host_session_runtime_sync,
                payloads,
            )
        except Exception as exc:
            self._host_session_runtime_registration_failure_count += 1
            retry_in = self._host_session_registration_backoff_seconds()
            self._host_session_runtime_next_attempt_at = now + retry_in
            logger.warning(
                (
                    "Host-session runtime auto-registration failed for "
                    "workspace=%s surface=%s: %s (retry in %.1fs)"
                ),
                self.workspace_id,
                self.surface,
                exc,
                retry_in,
            )
            return

        runtime_id = response.get("runtime_id")
        runtime_count = int(response.get("registered_runtime_count") or 1)
        self._host_session_runtime_registered = bool(response.get("registered"))
        if self._host_session_runtime_registered:
            self._host_session_runtime_last_registered_fingerprint = fingerprint
            self._host_session_runtime_last_success_at = now
            self._host_session_runtime_next_attempt_at = (
                now + self.HOST_SESSION_REGISTER_REFRESH_INTERVAL
            )
            self._host_session_runtime_registration_failure_count = 0
        logger.info(
            "Host-session runtime registered for workspace=%s surface=%s runtime_id=%s count=%s",
            self.workspace_id,
            self.surface,
            runtime_id or "-",
            runtime_count,
        )

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
            "attachments": result_message.get("attachments", []),
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

    async def _submit_result_via_rest(
        self,
        result_message: Dict[str, Any],
        *,
        queue_on_failure: bool = True,
    ) -> bool:
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
                self._pending_rest_results.pop(execution_id, None)
                self._persist_result_spool()
                return True
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    logger.info(
                        "REST result fallback for %s returned 404; "
                        "backend likely already accepted or resolved the execution.",
                        execution_id,
                    )
                    self._pending_rest_results.pop(execution_id, None)
                    self._persist_result_spool()
                    return True
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
                break
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
                break

        if queue_on_failure:
            self._remember_pending_rest_result(execution_id, result_message)
            logger.warning(
                "Queued result %s for retry after reconnect; pending=%d",
                execution_id,
                len(self._pending_rest_results),
            )
        return False

    def _remember_pending_rest_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> None:
        self._pending_rest_results[execution_id] = copy.deepcopy(result_message)
        self._pending_rest_results.move_to_end(execution_id)
        while len(self._pending_rest_results) > self.RECENT_RESULT_MAX_SIZE:
            self._pending_rest_results.popitem(last=False)
        self._persist_result_spool()

    def _schedule_pending_result_flush(self) -> None:
        if not self._pending_rest_results:
            return
        task = self._pending_rest_flush_task
        if task and not task.done():
            return
        task = self._start_background_task(self._flush_pending_results())
        self._pending_rest_flush_task = task
        task.add_done_callback(lambda _: setattr(self, "_pending_rest_flush_task", None))

    async def _flush_pending_results(self) -> None:
        if not self._pending_rest_results:
            return
        pending_items = list(self._pending_rest_results.items())
        logger.info("Flushing %d pending result(s) after reconnect", len(pending_items))
        for execution_id, result_message in pending_items:
            delivered = await self._submit_result_via_rest(
                result_message,
                queue_on_failure=False,
            )
            if delivered:
                self._pending_rest_results.pop(execution_id, None)

    def _prune_recent_results(self) -> None:
        now = time.monotonic()
        changed = False
        while self._recent_results:
            execution_id, (stored_at, _stored_at_wall, _result) = next(
                iter(self._recent_results.items())
            )
            if (
                len(self._recent_results) > self.RECENT_RESULT_MAX_SIZE
                or now - stored_at > self.RECENT_RESULT_TTL
            ):
                self._recent_results.pop(execution_id, None)
                changed = True
                continue
            break
        if changed:
            self._persist_result_spool()

    def _remember_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> None:
        self._recent_results[execution_id] = (
            time.monotonic(),
            time.time(),
            copy.deepcopy(result_message),
        )
        self._recent_results.move_to_end(execution_id)
        self._prune_recent_results()
        self._persist_result_spool()

    def _get_recent_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        self._prune_recent_results()
        cached = self._recent_results.get(execution_id)
        if not cached:
            return None
        _stored_at, _stored_at_wall, result_message = cached
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
        default=os.environ.get("MINDSCAPE_SURFACE", "").strip() or None,
        help="Surface type (required, or set MINDSCAPE_SURFACE)",
    )
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("MINDSCAPE_WORKSPACE_ROOT", os.getcwd()),
        help="Workspace root directory for task execution",
    )
    parser.add_argument(
        "--refresh-codex-seeds",
        action="store_true",
        help="Refresh remembered Codex host-session seeds and exit",
    )
    args = parser.parse_args()
    if args.refresh_codex_seeds and not args.surface:
        args.surface = "codex_cli"
    if not args.surface:
        parser.error("--surface is required (or set MINDSCAPE_SURFACE)")
    if not args.refresh_codex_seeds and not args.workspace_id:
        parser.error("--workspace-id is required (or set MINDSCAPE_WORKSPACE_ID)")

    if args.refresh_codex_seeds:
        refresh_host = (
            args.host
            or os.environ.get("MINDSCAPE_WS_HOST", "").strip()
            or "localhost:8200"
        )
        client = HostBridgeWSClient(
            workspace_id=args.workspace_id or "seed-refresh",
            host=refresh_host,
            auth_secret=args.auth_secret,
            client_id=args.client_id,
            surface=args.surface,
            task_handler=lambda _task: None,
        )
        print(json.dumps(client.refresh_codex_home_seeds(), ensure_ascii=False))
        return

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
        runtime_identity = _runtime_identity()
        logger.info(
            (
                "Received %s, shutting down... "
                "(workspace=%s surface=%s pid=%s ppid=%s pgid=%s "
                "xpc_service=%s active_tasks=%s)"
            ),
            sig.name,
            client.workspace_id,
            client.surface,
            runtime_identity.get("pid"),
            runtime_identity.get("ppid"),
            runtime_identity.get("pgid"),
            runtime_identity.get("xpc_service_name") or "-",
            client._active_tasks,
        )
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
