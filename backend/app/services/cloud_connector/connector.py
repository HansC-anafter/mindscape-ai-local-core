"""
Cloud Connector - Connection Management

Manages WebSocket connection to Cloud, handles reconnection with exponential backoff,
and coordinates transport and heartbeat components.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, WebSocketException

from .transport import TransportHandler
from .heartbeat import HeartbeatMonitor
from .messaging_handler import MessagingHandler

logger = logging.getLogger(__name__)


class CloudConnector:
    """
    Cloud Connector for Local-Core to Cloud communication.

    Manages WebSocket connection, automatic reconnection, and coordinates
    transport and heartbeat components.

    ⚠️ Hard Rule: This is an Execution Transport Adapter only.
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
            cloud_ws_url: Cloud WebSocket URL (default: from env CLOUD_WS_URL)
            device_id: Device identifier (default: auto-generated)
            tenant_id: Tenant identifier (default: from env or "local")
        """
        self.cloud_ws_url = cloud_ws_url or os.getenv(
            "CLOUD_WS_URL", "wss://agent.anafter.co/api/v1/executor/ws"
        )
        self.device_id = device_id or self._get_or_create_device_id()
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
        Get device token from site-hub.

        Returns:
            Device token

        Raises:
            Exception: If token retrieval fails
        """
        site_hub_url = os.getenv("SITE_HUB_URL", "https://site-hub.mindscape.ai")
        user_token = os.getenv("SITE_HUB_USER_TOKEN") or os.getenv("SITE_HUB_API_TOKEN")

        if not user_token:
            logger.warning(
                "SITE_HUB_USER_TOKEN not set, using mock token for development"
            )
            return "mock_device_token_for_development"

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{site_hub_url}/api/v1/device-tokens",
                    json={
                        "device_id": self.device_id,
                        "tenant_id": self.tenant_id,
                        "user_token": user_token,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                return data["token"]
        except Exception as e:
            logger.error(f"Failed to get device token: {e}")
            raise

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

            logger.info(f"Connecting to Cloud WebSocket: {self.cloud_ws_url}")

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

            logger.info("Connected to Cloud WebSocket")

            self.transport_handler = TransportHandler(self.websocket, self.device_id)
            self.heartbeat_monitor = HeartbeatMonitor(self.websocket)
            self.messaging_handler = MessagingHandler(
                websocket=self.websocket,
                device_id=self.device_id,
            )

            asyncio.create_task(self._message_loop())
            asyncio.create_task(self.heartbeat_monitor.start())

        except Exception as e:
            self._is_connecting = False
            self._is_connected = False
            logger.error(f"Failed to connect to Cloud: {e}")
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

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")

        self._is_connected = False
        self.websocket = None
        logger.info("Disconnected from Cloud")

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
