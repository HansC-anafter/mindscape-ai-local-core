"""
Cloud Connector - Messaging Handler

Handles messaging events from Cloud (LINE, WhatsApp, etc.)
and dispatches them to the IDE agent via AgentDispatchManager.

Flow:
  Site-Hub → CloudConnector WS → MessagingHandler → AgentDispatchManager → IDE
  IDE result → MessagingHandler → CloudConnector WS → Site-Hub → LINE Reply API
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class MessagingHandler:
    """
    Handles messaging events relayed from Site-Hub.

    Receives LINE/WhatsApp messages via the CloudConnector WebSocket,
    dispatches tasks to the IDE (Antigravity Agent) via AgentDispatchManager,
    and sends results back through the WebSocket for reply delivery.
    """

    def __init__(
        self,
        websocket: WebSocketClientProtocol,
        device_id: str,
        workspace_id: Optional[str] = None,
    ):
        """
        Initialize messaging handler.

        Args:
            websocket: WebSocket connection to Cloud
            device_id: Local-Core device identifier
            workspace_id: Default workspace ID (for 1:1 mapping)
        """
        self.websocket = websocket
        self.device_id = device_id
        self.workspace_id = workspace_id
        self._active_sessions: Dict[str, asyncio.Task] = {}

    async def handle(self, payload: Dict[str, Any]) -> None:
        """
        Handle incoming messaging event from Site-Hub.

        Expected payload format:
        {
            "channel": "line",
            "event_type": "message",
            "request_id": "unique-request-id",
            "user_id": "U1234...",
            "reply_token": "nHuyW...",
            "message": {
                "type": "text",
                "text": "幫我在 login.tsx 加一個忘記密碼按鈕"
            },
            "channel_config_id": "companion-line-workspace",
            "site_uuid": "bec8bf79-...",
            "timestamp": "2026-02-13T15:00:00Z"
        }
        """
        channel = payload.get("channel", "unknown")
        event_type = payload.get("event_type", "unknown")
        request_id = payload.get("request_id", f"msg_{uuid.uuid4().hex[:16]}")

        logger.info(
            f"[MessagingHandler] Received {channel}/{event_type} "
            f"request_id={request_id}"
        )

        if event_type != "message":
            logger.info(f"[MessagingHandler] Ignoring non-message event: {event_type}")
            await self._send_reply(
                request_id,
                payload,
                {
                    "status": "ignored",
                    "reason": f"Event type '{event_type}' not handled",
                },
            )
            return

        # Extract message text
        message = payload.get("message", {})
        text = message.get("text", "")

        if not text:
            logger.warning(f"[MessagingHandler] Empty message text for {request_id}")
            await self._send_reply(
                request_id,
                payload,
                {
                    "status": "error",
                    "error": "Empty message text",
                },
            )
            return

        # Dispatch to IDE agent
        task = asyncio.create_task(self._dispatch_to_ide(request_id, payload, text))
        self._active_sessions[request_id] = task

    async def _dispatch_to_ide(
        self,
        request_id: str,
        original_payload: Dict[str, Any],
        task_text: str,
    ) -> None:
        """
        Dispatch message as a task to the IDE agent.

        Uses AgentDispatchManager to send the task to a connected IDE client.
        """
        try:
            # Lazy import to avoid circular dependency
            from backend.app.routes.agent_websocket import (
                get_agent_dispatch_manager,
            )

            manager = get_agent_dispatch_manager()
            workspace_id = self.workspace_id

            if not workspace_id:
                # Attempt to resolve workspace_id from connected clients
                connected = manager.get_connected_workspaces()
                if connected:
                    workspace_id = connected[0]
                    logger.info(
                        f"[MessagingHandler] Auto-selected workspace: "
                        f"{workspace_id}"
                    )
                else:
                    logger.error(
                        "[MessagingHandler] No workspace available for dispatch"
                    )
                    await self._send_reply(
                        request_id,
                        original_payload,
                        {
                            "status": "error",
                            "error": "No IDE client connected",
                        },
                    )
                    return

            # Build dispatch payload
            execution_id = f"msg_{uuid.uuid4().hex[:16]}"
            dispatch_payload = {
                "execution_id": execution_id,
                "workspace_id": workspace_id,
                "type": "dispatch",
                "task": task_text,
                "allowed_tools": ["file", "terminal", "browser"],
                "max_duration": 600,
                "issued_at": _utc_now().isoformat(),
                "metadata": {
                    "source": "messaging",
                    "channel": original_payload.get("channel", "unknown"),
                    "user_id": original_payload.get("user_id"),
                    "request_id": request_id,
                },
            }

            logger.info(
                f"[MessagingHandler] Dispatching to IDE: "
                f"workspace={workspace_id}, exec={execution_id}"
            )

            # Dispatch and wait for result
            result = await manager.dispatch_and_wait(
                workspace_id=workspace_id,
                message=dispatch_payload,
                execution_id=execution_id,
            )

            logger.info(
                f"[MessagingHandler] IDE result received: "
                f"status={result.get('status', 'unknown')}"
            )

            # Send reply back to Site-Hub
            await self._send_reply(
                request_id,
                original_payload,
                {
                    "status": result.get("status", "completed"),
                    "output": result.get("output", ""),
                    "files_modified": result.get("files_modified", []),
                    "files_created": result.get("files_created", []),
                    "duration_seconds": result.get("duration_seconds", 0),
                },
            )

        except Exception as e:
            logger.error(f"[MessagingHandler] Dispatch failed: {e}", exc_info=True)
            await self._send_reply(
                request_id,
                original_payload,
                {
                    "status": "error",
                    "error": str(e),
                },
            )

        finally:
            self._active_sessions.pop(request_id, None)

    async def _send_reply(
        self,
        request_id: str,
        original_payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """
        Send messaging reply back to Site-Hub via WebSocket.

        Site-Hub will use this to call LINE Reply/Push API.
        """
        try:
            reply_message = {
                "type": "messaging_reply",
                "payload": {
                    "request_id": request_id,
                    "channel": original_payload.get("channel", "unknown"),
                    "user_id": original_payload.get("user_id"),
                    "reply_token": original_payload.get("reply_token"),
                    "channel_config_id": original_payload.get("channel_config_id"),
                    "result": result,
                    "device_id": self.device_id,
                    "timestamp": _utc_now().isoformat(),
                },
            }

            await self.websocket.send(json.dumps(reply_message))
            logger.info(
                f"[MessagingHandler] Reply sent for {request_id}: "
                f"status={result.get('status')}"
            )

        except Exception as e:
            logger.error(
                f"[MessagingHandler] Failed to send reply: {e}",
                exc_info=True,
            )
