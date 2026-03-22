"""
Cloud Connector - Connection Management

Manages WebSocket connection to the remote execution control plane, handles
reconnection with exponential backoff, and coordinates transport and heartbeat
components.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import httpx
import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, WebSocketException

from .transport import TransportHandler
from .heartbeat import HeartbeatMonitor
from .messaging_handler import MessagingHandler
from .activity_relay import ActivityRelay

logger = logging.getLogger(__name__)


class CloudConnector:
    """
    Cloud Connector for Local-Core to execution-control communication.

    Manages WebSocket connection, automatic reconnection, and coordinates
    transport and heartbeat components.

    Hard Rule: This is an Execution Transport Adapter only.
    It does NOT contain Cloud business logic or Cloud UI.
    """

    def __init__(
        self,
        cloud_ws_url: Optional[str] = None,
        device_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize Cloud Connector.

        Args:
            cloud_ws_url: Cloud WebSocket URL (resolved from DB → env → error)
            device_id: Device identifier (default: auto-generated)
            tenant_id: Tenant identifier (default: from env or "local")
        """
        self.cloud_ws_url = cloud_ws_url or self._resolve_ws_url()
        self.device_id = (
            device_id
            or (os.getenv("DEVICE_ID", "") or "").strip()
            or self._get_or_create_device_id()
        )
        self.tenant_id = tenant_id or os.getenv("TENANT_ID", "local")

        self.device_token: Optional[str] = None
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.transport_handler: Optional[TransportHandler] = None
        self.heartbeat_monitor: Optional[HeartbeatMonitor] = None
        self.messaging_handler: Optional[MessagingHandler] = None

        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 300.0
        self._is_connecting = False
        self._is_connected = False
        self._should_reconnect = True

    @staticmethod
    def _resolve_cloud_base_url() -> Optional[str]:
        """
        Read execution-control base URL from RuntimeEnvironment DB (config_url field).

        Falls back to explicit environment overrides. Returns None if not configured.
        """
        try:
            from app.database import get_db_postgres
            from app.models.runtime_environment import RuntimeEnvironment

            db = next(get_db_postgres())
            try:
                runtime = (
                    db.query(RuntimeEnvironment)
                    .filter(
                        RuntimeEnvironment.env_type == "cloud",
                        RuntimeEnvironment.is_enabled.is_(True),
                    )
                    .first()
                )
                if runtime and runtime.config_url:
                    logger.debug(
                        "Cloud base URL from DB runtime %s: %s",
                        runtime.id,
                        runtime.config_url,
                    )
                    return runtime.config_url.rstrip("/")
            finally:
                db.close()
        except Exception as e:
            logger.debug("Could not read cloud URL from DB: %s", e)

        return None

    @staticmethod
    def _resolve_execution_control_base_url() -> Optional[str]:
        """Resolve execution-control base URL from env or RuntimeEnvironment."""
        return (
            os.getenv("EXECUTION_CONTROL_API_URL")
            or os.getenv("SITE_HUB_API_URL")
            or os.getenv("CLOUD_API_URL")
            or CloudConnector._resolve_cloud_base_url()
        )

    def _resolve_ws_url(self) -> str:
        """
        Resolve WebSocket URL: explicit env → derived base URL → warning.

        Derives WSS URL from the execution-control base URL stored in the runtime DB.
        """
        env_ws = (
            os.getenv("EXECUTION_CONTROL_WS_URL")
            or os.getenv("SITE_HUB_WS_URL")
            or os.getenv("CLOUD_WS_URL")
        )
        if env_ws:
            return env_ws

        base = self._resolve_execution_control_base_url()
        if base:
            scheme = "wss" if base.startswith("https") else "ws"
            host = base.split("://", 1)[-1]
            return f"{scheme}://{host}/api/v1/executor/ws"

        logger.warning(
            "Execution-control WS URL not configured. "
            "Set Runtime Environments config_url or "
            "EXECUTION_CONTROL_WS_URL / SITE_HUB_WS_URL / CLOUD_WS_URL."
        )
        return ""

    def _get_or_create_device_id(self) -> str:
        """
        Get or create device ID.

        Returns:
            Device identifier
        """
        device_id_file = os.path.expanduser("~/.mindscape/device_id")
        os.makedirs(os.path.dirname(device_id_file), exist_ok=True)

        if os.path.exists(device_id_file):
            with open(device_id_file, "r") as f:
                return f.read().strip()

        device_id = f"device_{uuid.uuid4().hex[:16]}"
        with open(device_id_file, "w") as f:
            f.write(device_id)
        return device_id

    async def get_device_token(self) -> str:
        """
        Get device token for WebSocket authentication.

        Token resolution order:
        1. CLOUD_PROVIDER_TOKEN / CLOUD_API_TOKEN environment variable
        2. OAuth access_token from the cloud provider runtime in the database
        3. Raise ValueError if no valid token is available

        Returns:
            Access token for WebSocket authentication
        """
        # Priority 1: explicit env var
        user_token = os.getenv("CLOUD_PROVIDER_TOKEN") or os.getenv("CLOUD_API_TOKEN")

        # Priority 2: OAuth token from cloud provider runtime in DB
        if not user_token:
            user_token = await self._get_runtime_oauth_token()

        if not user_token:
            logger.error(
                "No auth token available for CloudConnector. "
                "Set CLOUD_PROVIDER_TOKEN / CLOUD_API_TOKEN env var, "
                "or connect an OAuth runtime in the database."
            )
            raise ValueError(
                "CloudConnector requires authentication. "
                "No OAuth token available (env vars not set, "
                "runtime OAuth token not found)."
            )

        logger.info("Using OAuth token for CloudConnector WebSocket authentication")
        return user_token

    async def _get_runtime_oauth_token(self) -> str | None:
        """
        Read OAuth access_token from a connected OAuth runtime in DB.

        Uses RuntimeAuthService.get_auth_headers() which handles automatic
        refresh of expired tokens using refresh_token grants.

        Returns:
            Access token string, or None if unavailable.
        """
        try:
            from app.database import get_db_postgres
            from app.models.runtime_environment import RuntimeEnvironment
            from app.services.runtime_auth_service import RuntimeAuthService

            db = next(get_db_postgres())
            try:
                runtimes = (
                    db.query(RuntimeEnvironment)
                    .filter(
                        RuntimeEnvironment.auth_type == "oauth2",
                        RuntimeEnvironment.auth_status.in_(["connected", "expired"]),
                    )
                    .all()
                )
                if not runtimes:
                    logger.debug("No connected OAuth runtimes found in DB")
                    return None

                svc = RuntimeAuthService()

                for runtime in runtimes:
                    if not runtime.auth_config:
                        continue
                    try:
                        headers = await svc.get_auth_headers(runtime, db)
                        auth_header = headers.get("Authorization", "")
                        if auth_header.startswith("Bearer "):
                            access_token = auth_header[7:]
                            logger.info(
                                "Retrieved OAuth token (with auto-refresh) from runtime %s",
                                runtime.id,
                            )
                            return access_token
                    except Exception as e:
                        logger.warning(
                            "Failed to get valid token from runtime %s: %s",
                            runtime.id,
                            e,
                        )
                logger.debug("All connected runtimes have empty access_token")
                return None
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to read runtime OAuth token: {e}")
            return None

    async def connect(self) -> None:
        """
        Establish WebSocket connection to Cloud.

        Handles authentication and sets up transport and heartbeat handlers.
        """
        if self._is_connecting or self._is_connected:
            logger.warning("Already connecting or connected")
            return

        self._is_connecting = True

        try:
            self.device_token = await self.get_device_token()

            # Build WSS URL with query params for device registry
            site_key = os.getenv("SITE_KEY", self.tenant_id)
            ws_url = (
                f"{self.cloud_ws_url}"
                f"?device_id={self.device_id}"
                f"&site_key={site_key}"
                f"&token={self.device_token}"
            )

            headers = {
                "Authorization": f"Bearer {self.device_token}",
                "X-Device-Id": self.device_id,
                "X-Tenant-Id": self.tenant_id,
            }

            logger.info(
                "Connecting to execution-control WebSocket: %s",
                self.cloud_ws_url,
            )

            ssl_context = None
            if self.cloud_ws_url.startswith("wss://"):
                # Force HTTP/1.1 via ALPN — GCP Load Balancer defaults to H2
                # which breaks WebSocket upgrade semantics (Connection: Upgrade)
                import ssl

                ssl_context = ssl.create_default_context()
                ssl_context.set_alpn_protocols(["http/1.1"])

            self.websocket = await websockets.connect(
                ws_url,
                additional_headers=headers,
                ssl=ssl_context,
                open_timeout=30,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10,
                compression=None,
                max_size=2**20,
            )

            self._is_connected = True
            self._is_connecting = False
            self._reconnect_attempts = 0
            self._reconnect_delay = 1.0

            logger.info("Connected to execution-control WebSocket")

            self.transport_handler = TransportHandler(self.websocket, self.device_id)
            self.heartbeat_monitor = HeartbeatMonitor(self.websocket)
            self.messaging_handler = MessagingHandler(
                websocket=self.websocket,
                device_id=self.device_id,
            )

            asyncio.create_task(self._message_loop())
            asyncio.create_task(self.heartbeat_monitor.start())

            # Start activity event relay (Redis → WS → Site-Hub)
            self.activity_relay = ActivityRelay(self.websocket, self.device_id)
            asyncio.create_task(self.activity_relay.start())

        except Exception as e:
            self._is_connecting = False
            self._is_connected = False
            logger.error(f"Failed to connect to execution control plane: {e}")
            if self._should_reconnect:
                await self._schedule_reconnect()

    async def disconnect(self) -> None:
        """
        Disconnect from Cloud.

        Stops reconnection attempts and closes WebSocket connection.
        """
        self._should_reconnect = False

        if self.heartbeat_monitor:
            await self.heartbeat_monitor.stop()

        # Stop activity relay
        if hasattr(self, "activity_relay") and self.activity_relay:
            await self.activity_relay.stop()
            self.activity_relay = None

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")

        self._is_connected = False
        self.websocket = None
        logger.info("Disconnected from execution control plane")

    async def _message_loop(self) -> None:
        """
        Main message loop for handling incoming WebSocket messages.
        """
        try:
            async for message in self.websocket:
                try:
                    if isinstance(message, str):
                        msg = json.loads(message)
                    else:
                        msg = json.loads(message.decode("utf-8"))

                    await self._handle_message(msg)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse WebSocket message: {e}")
                except Exception as e:
                    logger.error(f"Error handling WebSocket message: {e}")

        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self._is_connected = False
            if self._should_reconnect:
                await self._schedule_reconnect()
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self._is_connected = False
            if self._should_reconnect:
                await self._schedule_reconnect()

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """
        Handle incoming WebSocket message.

        Args:
            msg: Message dictionary
        """
        msg_type = msg.get("type")

        if msg_type == "execution_request":
            if self.transport_handler:
                await self.transport_handler.handle_execution_request(
                    msg.get("payload")
                )
        elif msg_type == "messaging_event":
            if self.messaging_handler:
                await self.messaging_handler.handle(msg.get("payload", {}))
            else:
                logger.warning("Received messaging_event but no handler configured")
        elif msg_type == "ping":
            if self.websocket:
                await self.websocket.send(json.dumps({"type": "pong"}))
                logger.debug("Sent pong in response to ping")
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _schedule_reconnect(self) -> None:
        """
        Schedule reconnection with exponential backoff.
        """
        if not self._should_reconnect:
            return

        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(
                f"Max reconnection attempts ({self._max_reconnect_attempts}) reached"
            )
            return

        self._reconnect_attempts += 1
        delay = min(
            self._reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            self._max_reconnect_delay,
        )

        logger.info(
            f"Reconnecting in {delay} seconds (attempt {self._reconnect_attempts})"
        )
        await asyncio.sleep(delay)

        await self.connect()

    @property
    def is_connected(self) -> bool:
        """Check if connected to Cloud."""
        return self._is_connected

    @property
    def device_id(self) -> str:
        """Get device ID."""
        return self._device_id

    @device_id.setter
    def device_id(self, value: str) -> None:
        """Set device ID."""
        self._device_id = value

    # ------------------------------------------------------------------
    # HTTP dispatch API  (used by execution_dispatch.py:dispatch_remote_execution)
    # ------------------------------------------------------------------

    def _get_http_client(self) -> httpx.AsyncClient:
        """Lazy-init an httpx client pointed at the execution-control REST API."""
        if not getattr(self, "_http_client", None):
            control_plane_api_url = self._resolve_execution_control_base_url()
            if not control_plane_api_url:
                raise ConnectionError(
                    "Execution control API URL not configured. "
                    "Set Runtime Environments config_url or "
                    "EXECUTION_CONTROL_API_URL / SITE_HUB_API_URL / CLOUD_API_URL."
                )
            api_key = os.getenv("CLOUD_API_KEY", "") or os.getenv(
                "CLOUD_PROVIDER_TOKEN", ""
            )
            self._http_client: Optional[httpx.AsyncClient] = httpx.AsyncClient(
                base_url=control_plane_api_url,
                headers={
                    "X-Device-Id": self._device_id,
                    "Authorization": f"Bearer {api_key}",
                },
                timeout=30.0,
            )
        return self._http_client

    async def start_remote_execution(
        self,
        tenant_id: str,
        playbook_code: str,
        request_payload: Dict[str, Any],
        workspace_id: Optional[str] = None,
        capability_code: Optional[str] = None,
        execution_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        job_type: str = "playbook",
        callback_payload: Optional[Dict[str, Any]] = None,
        target_device_id: Optional[str] = None,
        site_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch execution request to the execution control plane via HTTP.

        Called by execution_dispatch.dispatch_remote_execution().

        Args:
            tenant_id: Tenant identifier for control-plane routing
            playbook_code: Playbook to execute
            request_payload: Execution input data
            workspace_id: Optional workspace context
            capability_code: Optional capability identifier

        Returns:
            Execution record with id and state

        Raises:
            ConnectionError: If HTTP client cannot be initialised
            httpx.HTTPStatusError: On API failure
        """
        client = self._get_http_client()
        governance = (
            request_payload.get("_governance", {})
            if isinstance(request_payload, dict)
            and isinstance(request_payload.get("_governance"), dict)
            else {}
        )
        resolved_site_key = site_key or governance.get("site_key") or os.getenv(
            "SITE_KEY"
        ) or tenant_id
        response = await client.post(
            "/api/v1/executions",
            json={
                "tenant_id": tenant_id,
                "execution_id": execution_id,
                "trace_id": trace_id,
                "job_type": job_type,
                "playbook_code": playbook_code,
                "request_payload": request_payload,
                "workspace_id": workspace_id,
                "capability_code": capability_code,
                "device_id": target_device_id,
                "site_key": resolved_site_key,
                "callback_payload": callback_payload,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_remote_execution(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch remote execution status from the execution control plane."""
        client = self._get_http_client()
        params = {"tenant_id": tenant_id} if tenant_id else None
        response = await client.get(f"/api/v1/executions/{execution_id}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_remote_execution_result(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch remote execution terminal payload from the execution control plane."""
        client = self._get_http_client()
        params = {"tenant_id": tenant_id} if tenant_id else None
        response = await client.get(
            f"/api/v1/executions/{execution_id}/result",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def wait_for_remote_execution_terminal_result(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
        timeout_seconds: float = 900.0,
        poll_interval_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """Poll the execution control plane until a remote execution is terminal."""
        terminal_states = {"completed", "failed", "cancelled", "timeout"}
        started_at = datetime.now(timezone.utc)

        while True:
            execution = await self.get_remote_execution(
                execution_id,
                tenant_id=tenant_id,
            )
            state = str(execution.get("state") or "").strip().lower()
            if state in terminal_states:
                result = await self.get_remote_execution_result(
                    execution_id,
                    tenant_id=tenant_id,
                )
                return {
                    "status": state,
                    "execution": execution,
                    "result_payload": result.get("result_payload"),
                    "error_message": result.get("error_message"),
                    "completed_at": result.get("completed_at"),
                }

            elapsed_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed_seconds >= max(1.0, float(timeout_seconds)):
                raise TimeoutError(
                    f"Timed out waiting for remote execution {execution_id} "
                    f"after {timeout_seconds:.1f}s"
                )

            await asyncio.sleep(max(0.1, float(poll_interval_seconds)))
