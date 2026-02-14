"""
IDE-side WebSocket Client for Antigravity Agent

This script runs inside the IDE environment to:
  1. Connect to the Mindscape backend via WebSocket
  2. Authenticate using HMAC challenge-response
  3. Receive dispatched coding tasks
  4. Execute tasks via the Antigravity agent
  5. Send back ack, progress, and result messages

Usage:
    python ide_ws_client.py --workspace-id ws-123 [--host localhost:8000]
    python ide_ws_client.py --workspace-id ws-123 --auth-secret my_secret

Environment Variables:
    MINDSCAPE_WS_HOST       Backend host (default: localhost:8000)
    MINDSCAPE_AUTH_SECRET    HMAC auth secret (optional, skipped in dev mode)
    MINDSCAPE_WORKSPACE_ID  Workspace ID
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, Optional

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ide_ws_client")


class AntigravityWSClient:
    """
    IDE-side WebSocket client for receiving and executing tasks
    from the Mindscape backend.
    """

    # Reconnect settings
    RECONNECT_BASE_DELAY: float = 1.0
    RECONNECT_MAX_DELAY: float = 30.0
    RECONNECT_MAX_ATTEMPTS: int = 0  # 0 = unlimited

    # Heartbeat interval (should be < server's CLIENT_TIMEOUT)
    HEARTBEAT_INTERVAL: float = 25.0

    def __init__(
        self,
        workspace_id: str,
        host: str = "localhost:8000",
        auth_secret: Optional[str] = None,
        client_id: Optional[str] = None,
        surface: str = "antigravity",
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

    async def run(self) -> None:
        """Main entry point — connect with auto-reconnect."""
        self._running = True
        logger.info(f"Starting IDE WS client (workspace={self.workspace_id})")

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
        logger.info("IDE WS client stopped")

    # ============================================================
    #  Connection
    # ============================================================

    async def _connect_and_listen(self) -> None:
        """Single connection lifecycle."""
        logger.info(f"Connecting to {self.ws_url}")

        async with websockets.connect(self.ws_url) as ws:
            self._ws = ws
            self._reconnect_attempt = 0
            logger.info("Connected!")

            # Start heartbeat task
            heartbeat = asyncio.create_task(self._heartbeat_loop())

            try:
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        await self._handle_message(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {raw_msg[:100]}")
            finally:
                heartbeat.cancel()
                self._ws = None

    async def _heartbeat_loop(self) -> None:
        """Send periodic pings to keep connection alive."""
        while True:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            if self._ws:
                try:
                    await self._ws.send(json.dumps({"type": "ping"}))
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

        # 2. Execute
        start_time = time.monotonic()
        try:
            result = await self.task_handler(msg)
            duration = time.monotonic() - start_time

            # 3. Send result
            await self._send(
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
                    "governance": {
                        "output_hash": hashlib.sha256(
                            result.get("output", "").encode()
                        ).hexdigest(),
                        "summary": result.get("output", "")[:200],
                    },
                }
            )

            logger.info(
                f"Task completed: exec={execution_id}, "
                f"duration={duration:.1f}s, "
                f"status={result.get('status', 'completed')}"
            )

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(f"Task failed: {e}")
            await self._send(
                {
                    "type": "result",
                    "execution_id": execution_id,
                    "status": "failed",
                    "output": "",
                    "duration_seconds": duration,
                    "error": str(e),
                }
            )

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
        Default task handler — logs the task and returns a stub result.

        Replace this with actual Antigravity agent invocation in production.
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
        description="IDE-side WebSocket client for Antigravity Agent"
    )
    parser.add_argument(
        "--workspace-id",
        default=os.environ.get("MINDSCAPE_WORKSPACE_ID", ""),
        required=not bool(os.environ.get("MINDSCAPE_WORKSPACE_ID")),
        help="Workspace ID",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MINDSCAPE_WS_HOST", "localhost:8000"),
        help="Backend host (default: localhost:8000)",
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
        default="antigravity",
        help="Surface type (default: antigravity)",
    )
    args = parser.parse_args()

    client = AntigravityWSClient(
        workspace_id=args.workspace_id,
        host=args.host,
        auth_secret=args.auth_secret,
        client_id=args.client_id,
        surface=args.surface,
    )

    # Handle graceful shutdown
    loop = asyncio.new_event_loop()

    def shutdown(sig):
        logger.info(f"Received {sig.name}, shutting down...")
        loop.create_task(client.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: shutdown(s))

    try:
        loop.run_until_complete(client.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
