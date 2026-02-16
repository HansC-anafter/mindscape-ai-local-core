"""
Cloud Connector - Messaging Handler

Handles messaging events from Cloud (LINE, WhatsApp, etc.) and routes them
to the target workspace chat, treating the channel as a stateless input
surface identical to the workspace chat input box.

Flow:
  Site-Hub -> CloudConnector WS -> MessagingHandler -> workspace chat pipeline
  Workspace reply -> MessagingHandler -> CloudConnector WS -> Site-Hub -> LINE Reply API
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
    Routes messaging events from Site-Hub channels to workspace chat.

    Channels (LINE, WhatsApp, etc.) are stateless input surfaces.
    Messages are resolved to a target workspace via ChannelBinding
    and processed through the standard workspace chat pipeline.
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
            workspace_id: Default workspace ID (fallback if no binding found)
        """
        self.websocket = websocket
        self.device_id = device_id
        self.workspace_id = workspace_id
        self._active_sessions: Dict[str, asyncio.Task] = {}
        # Dedup guard: track in-progress request_ids to prevent duplicate LLM calls
        self._processed_requests: Dict[str, float] = {}
        self._dedup_ttl_seconds = 120  # 2 minute TTL

    def _is_duplicate_request(self, request_id: str) -> bool:
        """Check if request_id was already processed or is in-progress."""
        import time

        now = time.time()
        # Lazy cleanup of expired entries
        expired = [
            k
            for k, ts in self._processed_requests.items()
            if now - ts > self._dedup_ttl_seconds
        ]
        for k in expired:
            del self._processed_requests[k]

        return request_id in self._processed_requests

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
                "text": "Hello from LINE"
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

        # Dedup guard: skip if request_id already processed or in-progress
        if self._is_duplicate_request(request_id):
            logger.warning(
                f"[MessagingHandler] Duplicate request_id rejected: {request_id}"
            )
            await self._send_reply(
                request_id,
                payload,
                {
                    "status": "duplicate",
                    "reason": "Request already processed or in-progress",
                },
            )
            return

        import time

        self._processed_requests[request_id] = time.time()

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

        # Dispatch to workspace chat (channel is a stateless input surface)
        task = asyncio.create_task(
            self._dispatch_to_workspace(request_id, payload, text)
        )
        self._active_sessions[request_id] = task

    async def _resolve_workspace_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Resolve workspace_id from channel binding.

        Looks up the ChannelBinding table using channel_config_id from the payload.
        Falls back to self.workspace_id or the first available workspace.
        """
        channel_config_id = payload.get("channel_config_id")

        if channel_config_id:
            try:
                from backend.app.database.engine import SessionLocalCore
                from backend.app.models.channel_binding import ChannelBinding

                loop = asyncio.get_running_loop()

                def _lookup_binding():
                    db = SessionLocalCore()
                    try:
                        binding = (
                            db.query(ChannelBinding)
                            .filter(
                                ChannelBinding.channel_id == channel_config_id,
                                ChannelBinding.status == "active",
                            )
                            .first()
                        )
                        return binding.workspace_id if binding else None
                    finally:
                        db.close()

                workspace_id = await loop.run_in_executor(None, _lookup_binding)
                if workspace_id:
                    logger.info(
                        f"[MessagingHandler] Resolved workspace from binding: "
                        f"channel={channel_config_id} -> workspace={workspace_id}"
                    )
                    return workspace_id
                else:
                    logger.warning(
                        f"[MessagingHandler] No active binding for channel: "
                        f"{channel_config_id}"
                    )
            except Exception as e:
                logger.warning(f"[MessagingHandler] Binding lookup failed: {e}")

        # Fallback: use default workspace_id
        if self.workspace_id:
            logger.info(
                f"[MessagingHandler] Using default workspace: {self.workspace_id}"
            )
            return self.workspace_id

        # Last resort: pick first workspace from store
        try:
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            loop = asyncio.get_running_loop()
            workspaces = await loop.run_in_executor(None, store.list_workspaces)
            if workspaces:
                ws_id = (
                    workspaces[0].id
                    if hasattr(workspaces[0], "id")
                    else str(workspaces[0])
                )
                logger.info(
                    f"[MessagingHandler] Auto-selected first workspace: {ws_id}"
                )
                return ws_id
        except Exception as e:
            logger.warning(f"[MessagingHandler] Workspace lookup failed: {e}")

        return None

    async def _dispatch_to_workspace(
        self,
        request_id: str,
        original_payload: Dict[str, Any],
        message_text: str,
    ) -> None:
        """
        Dispatch message to workspace chat via direct service call.

        Calls ChatOrchestratorService.run_background_chat() in-process,
        then queries DB for the assistant reply to send back to Site-Hub.
        """
        try:
            # 1. Resolve target workspace
            workspace_id = await self._resolve_workspace_id(original_payload)
            if not workspace_id:
                logger.error("[MessagingHandler] No workspace available for dispatch")
                await self._send_reply(
                    request_id,
                    original_payload,
                    {
                        "status": "error",
                        "error": "No workspace bound to this channel",
                    },
                )
                return

            channel = original_payload.get("channel", "unknown")
            user_event_id = str(uuid.uuid4())

            logger.info(
                f"[MessagingHandler] Dispatching to workspace chat: "
                f"workspace={workspace_id}, channel={channel}, "
                f"event_id={user_event_id}, message={message_text[:60]}..."
            )

            # 2. Call ChatOrchestratorService directly (in-process, no HTTP)
            from backend.app.services.mindscape_store import MindscapeStore
            from backend.app.services.conversation_orchestrator import (
                ConversationOrchestrator,
            )
            from backend.app.services.chat_orchestrator_service import (
                ChatOrchestratorService,
            )
            from backend.app.models.workspace import WorkspaceChatRequest

            loop = asyncio.get_running_loop()
            store = MindscapeStore()

            workspace = await loop.run_in_executor(
                None, lambda: store.get_workspace(workspace_id)
            )
            if not workspace:
                logger.error(f"[MessagingHandler] Workspace {workspace_id} not found")
                await self._send_reply(
                    request_id,
                    original_payload,
                    {
                        "status": "error",
                        "error": f"Workspace {workspace_id} not found",
                    },
                )
                return

            profile_id = workspace.owner_user_id or "default-user"
            orchestrator = ConversationOrchestrator(store)
            service = ChatOrchestratorService(orchestrator)

            chat_request = WorkspaceChatRequest(
                message=message_text,
                mode="auto",
            )

            await service.run_background_chat(
                request=chat_request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                user_event_id=user_event_id,
            )

            # 3. Query DB for the latest assistant reply
            reply_text = ""
            try:
                events = await loop.run_in_executor(
                    None,
                    lambda: store.events.get_events_by_thread(
                        workspace_id=workspace_id,
                        thread_id=None,
                        limit=5,
                    ),
                )
                for evt in reversed(events or []):
                    actor_val = (
                        evt.actor.value
                        if hasattr(evt.actor, "value")
                        else str(evt.actor)
                    )
                    if (
                        actor_val == "assistant"
                        and evt.payload
                        and evt.payload.get("message")
                    ):
                        reply_text = evt.payload["message"]
                        break
            except Exception as db_err:
                logger.warning(
                    f"[MessagingHandler] Failed to fetch reply from DB: {db_err}"
                )

            logger.info(
                f"[MessagingHandler] Workspace chat completed: "
                f"reply_text_length={len(reply_text)}"
            )
            await self._send_reply(
                request_id,
                original_payload,
                {
                    "status": "completed",
                    "workspace_id": workspace_id,
                    "event_id": user_event_id,
                    "reply_text": reply_text,
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
