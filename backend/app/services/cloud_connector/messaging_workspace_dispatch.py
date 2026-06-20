"""Workspace dispatch and reply transport helpers for cloud messaging."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .messaging_reply_summary import (
    extract_session_metadata,
    format_dispatch_summary,
)

logger = logging.getLogger(__name__)


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def resolve_workspace_id(
    handler: Any, payload: Dict[str, Any]
) -> Optional[str]:
    """Resolve workspace_id from channel binding or configured fallbacks."""
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
            logger.warning(
                f"[MessagingHandler] No active binding for channel: "
                f"{channel_config_id}"
            )
        except Exception as e:
            logger.warning(f"[MessagingHandler] Binding lookup failed: {e}")

    if handler.workspace_id:
        logger.info(
            f"[MessagingHandler] Using default workspace: {handler.workspace_id}"
        )
        return handler.workspace_id

    try:
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        loop = asyncio.get_running_loop()
        workspaces = await loop.run_in_executor(None, store.list_workspaces)
        if workspaces:
            workspace_id = (
                workspaces[0].id if hasattr(workspaces[0], "id") else str(workspaces[0])
            )
            logger.info(
                f"[MessagingHandler] Auto-selected first workspace: {workspace_id}"
            )
            return workspace_id
    except Exception as e:
        logger.warning(f"[MessagingHandler] Workspace lookup failed: {e}")

    return None


async def dispatch_to_workspace(
    handler: Any,
    request_id: str,
    original_payload: Dict[str, Any],
    message_text: str,
) -> None:
    """Dispatch a cloud message to workspace chat through the existing service path."""
    try:
        workspace_id = await handler._resolve_workspace_id(original_payload)
        if not workspace_id:
            logger.error("[MessagingHandler] No workspace available for dispatch")
            await handler._send_reply(
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
        handler._latest_workspace_request[workspace_id] = request_id

        logger.info(
            f"[MessagingHandler] Dispatching to workspace chat: "
            f"workspace={workspace_id}, channel={channel}, "
            f"event_id={user_event_id}, message={message_text[:60]}..."
        )

        from backend.app.models.workspace import WorkspaceChatRequest
        from backend.app.routes.workspace_dependencies import (
            get_intent_pipeline,
            get_playbook_runner,
            get_store,
        )
        from backend.app.services.chat_orchestrator_service import (
            ChatOrchestratorService,
        )
        from backend.app.services.conversation_orchestrator import (
            ConversationOrchestrator,
        )

        store = get_store()

        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            logger.error(f"[MessagingHandler] Workspace {workspace_id} not found")
            await handler._send_reply(
                request_id,
                original_payload,
                {
                    "status": "error",
                    "error": f"Workspace {workspace_id} not found",
                },
            )
            return

        intent_pipeline = get_intent_pipeline(store)
        playbook_runner = get_playbook_runner()
        default_locale = workspace.default_locale if workspace.default_locale else "zh-TW"

        profile_id = workspace.owner_user_id or "default-user"
        orchestrator = ConversationOrchestrator(
            store=store,
            intent_pipeline=intent_pipeline,
            playbook_runner=playbook_runner,
            default_locale=default_locale,
        )
        service = ChatOrchestratorService(orchestrator)

        chat_request = WorkspaceChatRequest(
            message=message_text,
            mode="auto",
        )

        is_meeting = getattr(workspace, "meeting_enabled", False)
        page_id = None

        if is_meeting:
            page_id = str(uuid.uuid4())
            await handler._send_reply(
                request_id,
                original_payload,
                {
                    "status": "processing",
                    "workspace_id": workspace_id,
                    "page_id": page_id,
                    "summary": "已收到任務，正在進行任務會議，完成後可點選連結查看完整結果 📋",
                },
            )
            logger.info(f"[MessagingHandler] Quick reply sent: page_id={page_id}")

        pipeline_result = await service.run_background_chat(
            request=chat_request,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            user_event_id=user_event_id,
        )

        session_metadata = extract_session_metadata(pipeline_result)
        reply_text = ""
        try:
            events = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: store.events.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=10,
                ),
            )

            fallback_reply = ""
            for event in reversed(events or []):
                actor_val = (
                    event.actor.value if hasattr(event.actor, "value") else str(event.actor)
                )
                if (
                    actor_val == "assistant"
                    and event.payload
                    and event.payload.get("message")
                ):
                    if event.payload.get("response_to") == user_event_id:
                        reply_text = event.payload["message"]
                        break
                    if not fallback_reply:
                        fallback_reply = event.payload["message"]

            if not reply_text and fallback_reply:
                logger.warning(
                    f"[MessagingHandler] No correlated reply found for "
                    f"user_event_id={user_event_id}, using fallback"
                )
                reply_text = fallback_reply

        except Exception as db_err:
            logger.warning(
                f"[MessagingHandler] Failed to fetch reply from DB: {db_err}"
            )

        logger.info(
            f"[MessagingHandler] Workspace chat completed: "
            f"reply_text_length={len(reply_text)}"
        )

        latest = handler._latest_workspace_request.get(workspace_id)
        if latest and latest != request_id:
            logger.info(
                f"[MessagingHandler] Suppressing stale reply for "
                f"{request_id} (superseded by {latest})"
            )
            return

        if session_metadata:
            dispatch_text = format_dispatch_summary(session_metadata)
            if dispatch_text:
                reply_text += dispatch_text

        summary = await handler._generate_reply_summary(
            reply_text,
            workspace_id=workspace_id,
            profile_id=profile_id,
        )

        if page_id:
            meeting_md = await handler._build_meeting_detail_md(
                store, workspace_id, pipeline_result
            )
            page_content = reply_text + "\n\n" + meeting_md if meeting_md else reply_text
            await handler._send_reply(
                request_id,
                original_payload,
                {
                    "status": "page_update",
                    "workspace_id": workspace_id,
                    "event_id": user_event_id,
                    "page_id": page_id,
                    "page_content": page_content,
                    "reply_text": reply_text,
                    "summary": summary,
                    "session_metadata": session_metadata,
                },
            )
        else:
            await handler._send_reply(
                request_id,
                original_payload,
                {
                    "status": "completed",
                    "workspace_id": workspace_id,
                    "event_id": user_event_id,
                    "reply_text": reply_text,
                    "summary": summary,
                    "session_metadata": session_metadata,
                },
            )

    except Exception as e:
        logger.error(f"[MessagingHandler] Dispatch failed: {e}", exc_info=True)
        await handler._send_reply(
            request_id,
            original_payload,
            {
                "status": "error",
                "error": str(e),
            },
        )

    finally:
        handler._active_sessions.pop(request_id, None)


async def send_reply(
    handler: Any,
    request_id: str,
    original_payload: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """Send a messaging reply back to the cloud provider via WebSocket."""
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
                "device_id": handler.device_id,
                "timestamp": utc_now().isoformat(),
            },
        }

        await handler.websocket.send(json.dumps(reply_message))
        logger.info(
            f"[MessagingHandler] Reply sent for {request_id}: "
            f"status={result.get('status')}"
        )

    except Exception as e:
        logger.error(
            f"[MessagingHandler] Failed to send reply: {e}",
            exc_info=True,
        )
