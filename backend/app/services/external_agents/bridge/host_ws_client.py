"""Host WebSocket client compatibility entrypoint."""

import argparse
import asyncio
import json
import os
import signal
import sys
from collections import OrderedDict
from typing import Any, Callable, Coroutine, Dict, Optional, Set

from .host_ws_client_core.base import (
    UNKNOWN_EXECUTION_ERROR_RE,
    logger,
    _backend_api_url_candidates,
    _default_backend_api_url,
    _default_client_id,
    _env_flag,
    _env_float,
    _env_int,
    _format_url_host,
    _runtime_identity,
    _safe_path_component,
)
from .host_ws_client_core.backend_api_mixin import HostBridgeBackendApiMixin
from .host_ws_client_core.codex_home_mixin import HostBridgeCodexHomeMixin
from .host_ws_client_core.codex_registration_payload_mixin import (
    HostBridgeCodexRegistrationPayloadMixin,
)
from .host_ws_client_core.codex_seed_mixin import HostBridgeCodexSeedMixin
from .host_ws_client_core.dispatch_mixin import HostBridgeDispatchMixin
from .host_ws_client_core.polling_mixin import HostBridgePollingMixin
from .host_ws_client_core.registration_mixin import HostBridgeRegistrationMixin
from .host_ws_client_core.result_submission_mixin import HostBridgeResultSubmissionMixin
from .host_ws_client_core.send_mixin import HostBridgeSendMixin
from .host_ws_client_core.spool_mixin import HostBridgeSpoolMixin
from .host_ws_client_core.transport_mixin import HostBridgeTransportMixin


class HostBridgeWSClient(
    HostBridgeSpoolMixin,
    HostBridgeTransportMixin,
    HostBridgePollingMixin,
    HostBridgeDispatchMixin,
    HostBridgeBackendApiMixin,
    HostBridgeCodexHomeMixin,
    HostBridgeCodexSeedMixin,
    HostBridgeCodexRegistrationPayloadMixin,
    HostBridgeRegistrationMixin,
    HostBridgeResultSubmissionMixin,
    HostBridgeSendMixin,
):
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
    # When the backend closes an otherwise healthy idle socket, avoid
    # instant reconnect storms across every workspace/surface pair.
    CLEAN_IDLE_RECONNECT_DELAY: float = 15.0
    CLEAN_BUSY_RECONNECT_DELAY: float = 1.0
    CLEAN_IDLE_RECONNECT_SPREAD: float = 12.0
    CLEAN_BUSY_RECONNECT_SPREAD: float = 2.0
    BACKEND_HEALTHCHECK_TIMEOUT: float = 2.5
    BACKEND_UNHEALTHY_RECONNECT_DELAY: float = 30.0
    BACKEND_UNHEALTHY_RECONNECT_SPREAD: float = 20.0
    RESULT_REST_RETRY_ATTEMPTS: int = 4
    RESULT_REST_RETRY_BASE_DELAY: float = 1.0
    HOST_SESSION_REGISTER_TIMEOUT: float = 30.0
    HOST_SESSION_REGISTER_RETRY_INTERVAL: float = 15.0
    HOST_SESSION_REGISTER_REFRESH_INTERVAL: float = 300.0
    POLLING_RESERVE_MAX_DELAY: float = 30.0
    POLLING_WAIT_SECONDS: float = 5.0
    POLLING_LEASE_SECONDS: float = 60.0
    POLLING_HEARTBEAT_INTERVAL: float = 25.0
    WS_FORBIDDEN_POLLING_THRESHOLD: int = 3
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
        self.client_id = client_id or _default_client_id(
            workspace_id=workspace_id,
            surface=normalized_surface,
        )
        self.surface = normalized_surface
        self.task_handler = task_handler or self._default_task_handler
        self.owner_user_id = os.environ.get("MINDSCAPE_OWNER_USER_ID", "").strip()

        self._ws = None
        self._running = False
        self._reconnect_attempt = 0
        self._pong_received: Optional[asyncio.Event] = None
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
        self.CLEAN_IDLE_RECONNECT_DELAY = _env_float(
            "MINDSCAPE_WS_IDLE_RECONNECT_DELAY",
            self.CLEAN_IDLE_RECONNECT_DELAY,
            minimum=1.0,
        )
        self.CLEAN_BUSY_RECONNECT_DELAY = _env_float(
            "MINDSCAPE_WS_BUSY_RECONNECT_DELAY",
            self.CLEAN_BUSY_RECONNECT_DELAY,
            minimum=0.1,
        )
        self.CLEAN_IDLE_RECONNECT_SPREAD = _env_float(
            "MINDSCAPE_WS_IDLE_RECONNECT_SPREAD",
            self.CLEAN_IDLE_RECONNECT_SPREAD,
            minimum=0.0,
        )
        self.CLEAN_BUSY_RECONNECT_SPREAD = _env_float(
            "MINDSCAPE_WS_BUSY_RECONNECT_SPREAD",
            self.CLEAN_BUSY_RECONNECT_SPREAD,
            minimum=0.0,
        )
        self.PONG_TIMEOUT = _env_float(
            "MINDSCAPE_WS_PONG_TIMEOUT",
            self.PONG_TIMEOUT,
            minimum=1.0,
        )
        self.BACKEND_HEALTHCHECK_TIMEOUT = _env_float(
            "MINDSCAPE_WS_BACKEND_HEALTHCHECK_TIMEOUT",
            self.BACKEND_HEALTHCHECK_TIMEOUT,
            minimum=0.2,
        )
        self.BACKEND_UNHEALTHY_RECONNECT_DELAY = _env_float(
            "MINDSCAPE_WS_BACKEND_UNHEALTHY_RECONNECT_DELAY",
            self.BACKEND_UNHEALTHY_RECONNECT_DELAY,
            minimum=1.0,
        )
        self.BACKEND_UNHEALTHY_RECONNECT_SPREAD = _env_float(
            "MINDSCAPE_WS_BACKEND_UNHEALTHY_RECONNECT_SPREAD",
            self.BACKEND_UNHEALTHY_RECONNECT_SPREAD,
            minimum=0.0,
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
        self._dispatch_lock: Optional[asyncio.Lock] = None
        self._dispatch_lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._dispatch_tasks: Dict[str, asyncio.Task] = {}
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
        self._load_result_spool()
        self._host_session_runtime_registered = False
        self._host_session_runtime_last_attempt_fingerprint: Optional[str] = None
        self._host_session_runtime_last_registered_fingerprint: Optional[str] = None
        self._host_session_runtime_next_attempt_at: float = 0.0
        self._host_session_runtime_last_success_at: float = 0.0
        self._host_session_runtime_registration_failure_count: int = 0
        self._transport_mode = "ws"
        self._ws_forbidden_count = 0


def _host_runtime_session_bridge_enabled(surface: str) -> bool:
    return surface == "codex_cli" and _env_flag(
        "MINDSCAPE_ENABLE_HOST_RUNTIME_SESSION_BRIDGE",
        True,
    )


def _host_runtime_session_bridge_id(client: HostBridgeWSClient) -> str:
    explicit_bridge_id = os.environ.get("HOST_RUNTIME_BRIDGE_ID", "").strip()
    if explicit_bridge_id:
        return explicit_bridge_id
    return f"hostrt-shared-{_safe_path_component(client.client_id or client.workspace_id)}"


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
        default=os.environ.get("MINDSCAPE_CLIENT_ID") or None,
        help="Client ID (defaults to MINDSCAPE_CLIENT_ID or stable workspace/surface ID)",
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
        os.environ["MINDSCAPE_BACKEND_API_URL"] = _default_backend_api_url(args.host)
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

    host_runtime_client = None
    if _host_runtime_session_bridge_enabled(args.surface):
        from backend.app.services.host_runtime_sessions.bridge_client import (
            HostRuntimeSessionBridgeClient,
        )

        runtime_model = os.environ.get("HOST_RUNTIME_MODEL", "").strip() or None
        host_runtime_client = HostRuntimeSessionBridgeClient(
            host=args.host,
            bridge_id=_host_runtime_session_bridge_id(client),
            workspace_ids=[args.workspace_id],
            runtime_surface=args.surface,
            runtime_id=args.surface,
            workspace_root=args.workspace_root,
            max_duration=max(1, _env_int("HOST_RUNTIME_MAX_DURATION", 600)),
            model=runtime_model,
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
        if host_runtime_client is not None:
            loop.create_task(host_runtime_client.stop())
        loop.create_task(client.stop())

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: shutdown(s))
    except NotImplementedError:
        # Windows: add_signal_handler is not supported, use signal.signal fallback
        signal.signal(signal.SIGINT, lambda s, f: shutdown(signal.SIGINT))

    async def run_bridge_clients():
        host_runtime_task: Optional[asyncio.Task] = None
        if host_runtime_client is not None:
            logger.info(
                (
                    "Starting Host Runtime Session registration through shared "
                    "CLI bridge (workspace=%s surface=%s bridge_id=%s)"
                ),
                client.workspace_id,
                client.surface,
                host_runtime_client.bridge_id,
            )
            host_runtime_task = asyncio.create_task(host_runtime_client.run())
        try:
            await client.run()
        finally:
            if host_runtime_client is not None:
                await host_runtime_client.stop()
            if host_runtime_task is not None:
                host_runtime_task.cancel()
                await asyncio.gather(host_runtime_task, return_exceptions=True)

    try:
        loop.run_until_complete(run_bridge_clients())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
