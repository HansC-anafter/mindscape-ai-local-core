"""
Cloud Connector - Messaging Handler

Handles messaging events from Cloud (LINE, WhatsApp, etc.) and routes them
to the target workspace chat, treating the channel as a stateless input
surface identical to the workspace chat input box.

Flow:
  Cloud Provider -> CloudConnector WS -> MessagingHandler -> workspace chat pipeline
  Workspace reply -> MessagingHandler -> CloudConnector WS -> Cloud Provider -> LINE Reply API
"""

import asyncio
import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


_ASSET_UPLOAD_BASE_ENV_KEYS = (
    "MINDSCAPE_CLOUD_INTEGRATION_API_BASE",
    "MINDSCAPE_CLOUD_GENERATION_API_BASE",
    "CLOUD_PROVIDER_API_BASE",
    "SITE_HUB_API_BASE",
    "SITE_HUB_API_URL",
    "EXECUTION_CONTROL_API_URL",
    "CLOUD_API_URL",
)

_ASSET_UPLOAD_TOKEN_ENV_KEYS = (
    "MINDSCAPE_CLOUD_INTEGRATION_UPLOAD_TOKEN",
    "CLOUD_PROVIDER_UPLOAD_TOKEN",
    "SITE_HUB_UPLOAD_TOKEN",
    "SITE_HUB_API_TOKEN",
)


def _clean_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _append_unique_text(values: List[str], value: Optional[str]) -> None:
    if value and value not in values:
        values.append(value)


def _is_public_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _resolve_asset_upload_base() -> Optional[str]:
    for key in _ASSET_UPLOAD_BASE_ENV_KEYS:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip().rstrip("/")
    return None


def _resolve_asset_upload_token() -> Optional[str]:
    for key in _ASSET_UPLOAD_TOKEN_ENV_KEYS:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def _candidate_file_path(payload: Dict[str, Any]) -> Optional[str]:
    metadata = _as_mapping(payload.get("metadata"))
    for key in ("actual_file_path", "file_path", "storage_ref", "path", "uri"):
        value = payload.get(key) or metadata.get(key)
        if _is_public_url(value):
            continue
        cleaned = _clean_text(value)
        if cleaned and (cleaned.startswith("/") or "/" in cleaned):
            return cleaned
    return None


def _candidate_public_url(payload: Dict[str, Any]) -> Optional[str]:
    metadata = _as_mapping(payload.get("metadata"))
    for key in ("public_url", "url", "external_url", "asset_url", "download_url"):
        value = payload.get(key) or metadata.get(key)
        if _is_public_url(value):
            return str(value).strip()
    storage_ref = payload.get("storage_ref") or metadata.get("storage_ref")
    return str(storage_ref).strip() if _is_public_url(storage_ref) else None


def _asset_candidate_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = _as_mapping(payload.get("metadata"))
    file_path = _candidate_file_path(payload)
    public_url = _candidate_public_url(payload)
    artifact_id = _clean_text(
        payload.get("artifact_id")
        or payload.get("id")
        or metadata.get("artifact_id")
    )
    artifact_kind = _clean_text(
        payload.get("artifact_kind")
        or payload.get("artifact_type")
        or payload.get("type")
        or metadata.get("artifact_kind")
        or metadata.get("artifact_type")
    )

    has_asset_shape = bool(file_path or public_url) or any(
        key in payload or key in metadata
        for key in (
            "artifact_id",
            "artifact_kind",
            "artifact_type",
            "actual_file_path",
            "file_path",
            "storage_ref",
            "external_url",
        )
    )
    if not has_asset_shape:
        return None

    title = _clean_text(
        payload.get("title")
        or payload.get("name")
        or metadata.get("title")
        or metadata.get("name")
    )
    if not title and file_path:
        title = Path(file_path).name
    if not title and public_url:
        title = Path(public_url.split("?", 1)[0]).name or "artifact"
    if not title and artifact_id:
        title = artifact_id

    return {
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "title": title,
        "file_path": file_path,
        "url": public_url,
    }


def _collect_asset_candidates(value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 8:
        return []

    found: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        candidate = _asset_candidate_from_payload(value)
        if candidate:
            found.append(candidate)
        for key, nested in value.items():
            if key == "metadata":
                continue
            found.extend(_collect_asset_candidates(nested, depth=depth + 1))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_asset_candidates(item, depth=depth + 1))
    return _dedupe_asset_candidates(found)


def _collect_execution_ids(value: Any, *, depth: int = 0) -> List[str]:
    if depth > 8:
        return []
    found: List[str] = []
    if isinstance(value, dict):
        _append_unique_text(found, _clean_text(value.get("execution_id")))
        for nested in value.values():
            for execution_id in _collect_execution_ids(nested, depth=depth + 1):
                _append_unique_text(found, execution_id)
    elif isinstance(value, list):
        for item in value:
            for execution_id in _collect_execution_ids(item, depth=depth + 1):
                _append_unique_text(found, execution_id)
    return found


def _dedupe_asset_candidates(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: Dict[Any, Dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate.get("artifact_id") or (
            candidate.get("file_path"),
            candidate.get("url"),
            candidate.get("title"),
        )
        existing = seen.get(key)
        if existing:
            for field in ("file_path", "url", "title", "artifact_kind"):
                if not existing.get(field) and candidate.get(field):
                    existing[field] = candidate[field]
            continue
        seen[key] = candidate
        deduped.append(candidate)
    return deduped


def _asset_candidate_from_model(artifact: Any) -> Optional[Dict[str, Any]]:
    if artifact is None:
        return None
    metadata = _as_mapping(getattr(artifact, "metadata", None))
    storage_ref = _clean_text(getattr(artifact, "storage_ref", None))
    payload = {
        "artifact_id": _clean_text(getattr(artifact, "id", None)),
        "artifact_kind": _clean_text(
            getattr(getattr(artifact, "artifact_type", None), "value", None)
            or getattr(artifact, "artifact_type", None)
        ),
        "title": _clean_text(getattr(artifact, "title", None)),
        "storage_ref": storage_ref,
        "metadata": metadata,
    }
    return _asset_candidate_from_payload(payload)


async def _upload_page_asset(
    file_path: Path,
    *,
    workspace_id: str,
) -> Optional[str]:
    if not file_path.exists() or not file_path.is_file():
        return None

    base = _resolve_asset_upload_base()
    if not base:
        return None

    upload_url = f"{base}/api/v1/assets/upload"
    token = _resolve_asset_upload_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            with file_path.open("rb") as file_handle:
                response = await client.post(
                    upload_url,
                    headers=headers,
                    files={"file": (file_path.name, file_handle, mime_type)},
                    data={
                        "workspace_id": workspace_id,
                        "media_type": "meeting_artifact",
                        "filename": file_path.name,
                    },
                )
        response.raise_for_status()
        payload = response.json()
        return _clean_text(payload.get("url"))
    except Exception as exc:
        logger.warning(
            "[MessagingHandler] Result page asset upload failed: file=%s error=%s",
            file_path,
            exc,
        )
        return None


async def _materialize_page_assets(
    candidates: List[Dict[str, Any]],
    *,
    workspace_id: str,
) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    for candidate in _dedupe_asset_candidates(candidates)[:12]:
        file_path_text = _clean_text(candidate.get("file_path"))
        public_url = _clean_text(candidate.get("url"))
        file_name = Path(file_path_text).name if file_path_text else None

        if not public_url and file_path_text:
            public_url = await _upload_page_asset(
                Path(file_path_text),
                workspace_id=workspace_id,
            )

        title = (
            _clean_text(candidate.get("title"))
            or file_name
            or _clean_text(candidate.get("artifact_id"))
            or "artifact"
        )
        assets.append(
            {
                "title": title,
                "filename": file_name,
                "url": public_url,
                "artifact_id": _clean_text(candidate.get("artifact_id")),
                "artifact_kind": _clean_text(candidate.get("artifact_kind")),
            }
        )
    return assets


def _escape_markdown_label(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def _format_page_assets_md(assets: List[Dict[str, Any]]) -> str:
    if not assets:
        return ""

    lines = ["## 📎 產出檔案", ""]
    for asset in assets:
        label = _escape_markdown_label(
            _clean_text(asset.get("title"))
            or _clean_text(asset.get("filename"))
            or _clean_text(asset.get("artifact_id"))
            or "artifact"
        )
        details = [
            item
            for item in (
                _clean_text(asset.get("artifact_kind")),
                (
                    f"`{asset.get('artifact_id')}`"
                    if _clean_text(asset.get("artifact_id"))
                    else None
                ),
            )
            if item
        ]
        suffix = f" — {' · '.join(details)}" if details else ""
        url = _clean_text(asset.get("url"))
        if url:
            lines.append(f"- [{label}]({url}){suffix}")
        else:
            lines.append(f"- {label}{suffix}（已產出，尚未建立公開下載連結）")
    lines.append("")
    return "\n".join(lines)


class MessagingHandler:
    """
    Routes messaging events from cloud provider channels to workspace chat.

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
        # Supersede: track latest request per workspace to suppress stale replies
        self._latest_workspace_request: Dict[str, str] = {}

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
        Handle incoming messaging event from cloud provider.

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
        then queries DB for the assistant reply to send back to the cloud provider.
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

            # Mark this request as the latest for this workspace
            self._latest_workspace_request[workspace_id] = request_id

            logger.info(
                f"[MessagingHandler] Dispatching to workspace chat: "
                f"workspace={workspace_id}, channel={channel}, "
                f"event_id={user_event_id}, message={message_text[:60]}..."
            )

            # 2. Call ChatOrchestratorService directly (in-process, no HTTP)
            from backend.app.routes.workspace_dependencies import (
                get_store,
                get_intent_pipeline,
                get_playbook_runner,
            )
            from backend.app.services.conversation_orchestrator import (
                ConversationOrchestrator,
            )
            from backend.app.services.chat_orchestrator_service import (
                ChatOrchestratorService,
            )
            from backend.app.models.workspace import WorkspaceChatRequest

            store = get_store()

            workspace = await store.get_workspace(workspace_id)
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

            intent_pipeline = get_intent_pipeline(store)
            playbook_runner = get_playbook_runner()
            default_locale = (
                workspace.default_locale if workspace.default_locale else "zh-TW"
            )

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

            # ── Phase 1: Quick reply for meeting-enabled workspaces only ──
            is_meeting = getattr(workspace, "meeting_enabled", False)
            page_id = None

            if is_meeting:
                page_id = str(uuid.uuid4())
                await self._send_reply(
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

            # ── Phase 2: Run the pipeline (meeting or chat) ──
            pipeline_result = await service.run_background_chat(
                request=chat_request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                user_event_id=user_event_id,
            )

            # Extract meeting session metadata from pipeline result
            session_metadata = _extract_session_metadata(pipeline_result)

            # 3. Query DB for the assistant reply correlated to this request
            reply_text = ""
            try:
                events = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: store.events.get_events_by_workspace(
                        workspace_id=workspace_id,
                        limit=10,
                    ),
                )

                # First pass: find correlated reply (response_to == user_event_id)
                fallback_reply = ""
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
                        if evt.payload.get("response_to") == user_event_id:
                            reply_text = evt.payload["message"]
                            break
                        # Keep first assistant event as fallback
                        if not fallback_reply:
                            fallback_reply = evt.payload["message"]

                # Fallback: use first assistant event if no correlated reply found
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

            # Supersede check: skip reply if a newer request arrived
            latest = self._latest_workspace_request.get(workspace_id)
            if latest and latest != request_id:
                logger.info(
                    f"[MessagingHandler] Suppressing stale reply for "
                    f"{request_id} (superseded by {latest})"
                )
                return

            # Append formatted dispatch summary to reply text
            if session_metadata:
                dispatch_text = _format_dispatch_summary(session_metadata)
                if dispatch_text:
                    reply_text += dispatch_text

            # Generate concise summary for LINE rich card
            summary = await self._generate_reply_summary(
                reply_text,
                workspace_id=workspace_id,
                profile_id=profile_id,
            )

            if page_id:
                # ── Phase 3: Meeting path — update the pre-created page ──
                meeting_md = await self._build_meeting_detail_md(
                    store, workspace_id, pipeline_result
                )
                page_content = (
                    reply_text + "\n\n" + meeting_md if meeting_md else reply_text
                )
                await self._send_reply(
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
                # ── Non-meeting path — single reply as before ──
                await self._send_reply(
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

    async def _build_meeting_detail_md(
        self,
        store,
        workspace_id: str,
        pipeline_result,
    ) -> str:
        """Build Markdown with full meeting discussion, actions, and stats.

        Returns empty string for non-meeting flows.
        """
        if not pipeline_result:
            return ""

        session_id = getattr(pipeline_result, "meeting_session_id", None)
        if not session_id:
            return ""

        try:
            events = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: store.events.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=100,
                ),
            )

            if not events:
                return ""

            sections = []
            sections.append("---")
            sections.append("## 📋 會議討論紀錄")
            sections.append("")

            # Collect turns by round
            current_round = 0
            for evt in events:
                evt_type = evt.type if hasattr(evt, "type") else ""
                payload = evt.payload or {}

                if evt_type == "meeting_round":
                    current_round = payload.get("round", current_round + 1)
                    sections.append(f"### 第 {current_round} 輪")
                    sections.append("")

                elif evt_type == "agent_turn":
                    role = payload.get("role", "unknown")
                    content = payload.get("content", "")
                    role_label = {
                        "facilitator": "🎯 Facilitator",
                        "planner": "📐 Planner",
                        "critic": "🔍 Critic",
                    }.get(role, role)
                    if content:
                        # Trim very long turns for readability
                        if len(content) > 800:
                            content = content[:800] + "…"
                        sections.append(f"**{role_label}**")
                        sections.append(content)
                        sections.append("")

            # Action items
            action_items = [
                e
                for e in events
                if (e.type if hasattr(e, "type") else "") == "action_item"
            ]
            if action_items:
                sections.append("## ⚡ 行動項目")
                sections.append("")
                for i, ai in enumerate(action_items, 1):
                    p = ai.payload or {}
                    intent = p.get("intent", p.get("description", ""))
                    tool = p.get("tool_name", p.get("playbook_code", ""))
                    line = f"{i}. {intent}"
                    if tool:
                        line += f" (`{tool}`)"
                    sections.append(line)
                sections.append("")

            # Decisions
            decisions = [
                e
                for e in events
                if (e.type if hasattr(e, "type") else "") == "decision_final"
            ]
            if decisions:
                sections.append("## ✅ 決策")
                sections.append("")
                for d in decisions:
                    p = d.payload or {}
                    sections.append(f"- {p.get('summary', p.get('decision', ''))}")
                sections.append("")

            # Stats
            quality = getattr(pipeline_result, "quality_score", None)
            if quality is not None:
                sections.append("## 📊 統計")
                sections.append("")
                sections.append(f"- 質量分數: {quality:.0%}")
                task_ir = getattr(pipeline_result, "task_ir_id", None)
                if task_ir:
                    sections.append(f"- Task IR: `{task_ir}`")
                sections.append("")

            assets_md = await self._build_meeting_assets_md(
                store, workspace_id, pipeline_result
            )
            if assets_md:
                sections.append(assets_md)

            # Only return if we captured meaningful content
            if len(sections) <= 3:
                return ""

            return "\n".join(sections)

        except Exception as e:
            logger.warning(f"[MessagingHandler] Failed to build meeting detail: {e}")
            return ""

    async def _build_meeting_assets_md(
        self,
        store,
        workspace_id: str,
        pipeline_result,
    ) -> str:
        """Build a public-result-page section for meeting/AOL artifacts."""
        candidates: List[Dict[str, Any]] = []

        for attr in ("task_ir_artifacts", "artifact_assets"):
            raw_items = getattr(pipeline_result, attr, None) or []
            if isinstance(raw_items, list):
                for item in raw_items:
                    candidates.extend(_collect_asset_candidates(item))

        for file_path in list(
            getattr(pipeline_result, "artifact_file_paths", None) or []
        ):
            candidates.append(
                {"file_path": file_path, "title": Path(str(file_path)).name}
            )

        artifact_ids = [
            item
            for item in list(getattr(pipeline_result, "artifact_ids", None) or [])
            if _clean_text(item)
        ]
        for artifact_id in artifact_ids:
            candidates.append({"artifact_id": artifact_id, "title": artifact_id})

        dispatch_result = getattr(pipeline_result, "dispatch_result", None)
        candidates.extend(_collect_asset_candidates(dispatch_result))

        artifacts_store = getattr(store, "artifacts", None)
        if artifacts_store:
            for artifact_id in artifact_ids:
                try:
                    artifact = await asyncio.to_thread(
                        artifacts_store.get_artifact, artifact_id
                    )
                    candidate = _asset_candidate_from_model(artifact)
                    if candidate:
                        candidates.append(candidate)
                except Exception as exc:
                    logger.warning(
                        "[MessagingHandler] Failed to load artifact %s: %s",
                        artifact_id,
                        exc,
                    )

            execution_ids = _collect_execution_ids(dispatch_result)
            for execution_id in execution_ids[:12]:
                try:
                    artifacts = await asyncio.to_thread(
                        artifacts_store.list_by_execution_id, execution_id
                    )
                    for artifact in artifacts or []:
                        candidate = _asset_candidate_from_model(artifact)
                        if candidate:
                            candidates.append(candidate)
                except Exception as exc:
                    logger.warning(
                        "[MessagingHandler] Failed to load execution artifacts %s: %s",
                        execution_id,
                        exc,
                    )

            task_ir_id = _clean_text(getattr(pipeline_result, "task_ir_id", None))
            if task_ir_id and hasattr(artifacts_store, "list_artifacts_by_task"):
                try:
                    artifacts = await asyncio.to_thread(
                        artifacts_store.list_artifacts_by_task, task_ir_id
                    )
                    for artifact in artifacts or []:
                        candidate = _asset_candidate_from_model(artifact)
                        if candidate:
                            candidates.append(candidate)
                except Exception as exc:
                    logger.warning(
                        "[MessagingHandler] Failed to load task artifacts %s: %s",
                        task_ir_id,
                        exc,
                    )

        assets = await _materialize_page_assets(
            _dedupe_asset_candidates(candidates),
            workspace_id=workspace_id,
        )
        return _format_page_assets_md(assets)

    async def _send_reply(
        self,
        request_id: str,
        original_payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """
        Send messaging reply back to the cloud provider via WebSocket.

        The cloud provider will use this to call LINE Reply/Push API.
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

    async def _generate_reply_summary(
        self,
        reply_text: str,
        *,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> str:
        """
        Generate a concise summary (<=100 chars) for LINE Flex card display.

        Uses governed route selection for quality summarization.
        Falls back to smart truncation at sentence boundary on failure.

        Args:
            reply_text: Full AI response text

        Returns:
            Concise summary string, max 100 characters
        """
        # Short replies don't need summarization
        if len(reply_text) <= 100:
            return reply_text

        # Try LLM-based summary
        try:
            from backend.app.services.config_store import ConfigStore
            from backend.app.services.llm.workspace_routed_chat import (
                chat_completion_with_workspace_route,
            )
            from backend.app.services.playbook.llm_provider_manager import (
                PlaybookLLMProviderManager,
            )
            from backend.app.shared.llm_utils import build_prompt

            messages = build_prompt(
                user_prompt=(
                    "Summarize the following AI response in one sentence, "
                    "max 80 characters. Use the same language as the "
                    "original text. Output ONLY the summary, nothing else."
                    f"\n\n{reply_text[:2000]}"
                )
            )
            result = await chat_completion_with_workspace_route(
                messages=messages,
                workspace_id=workspace_id,
                profile_id=profile_id or "default-user",
                llm_provider_manager=PlaybookLLMProviderManager(ConfigStore()),
                purpose="cloud_connector_reply_summary",
                stage_name="response_formatting",
                risk_level="read",
                max_tokens=60,
                temperature=0.3,
            )
            summary = ""
            if isinstance(result, str):
                summary = result.strip()
            elif isinstance(result, dict):
                summary = str(result.get("content") or result.get("text") or "").strip()

            if summary and len(summary) <= 100:
                logger.info(
                    f"[MessagingHandler] Governed summary generated: "
                    f"{len(summary)} chars"
                )
                return summary

        except Exception as llm_err:
            logger.warning(
                f"[MessagingHandler] LLM summary failed, using truncation: "
                f"{llm_err}"
            )

        # Fallback: smart truncation at sentence boundary
        return self._truncate_at_boundary(reply_text, max_len=100)

    @staticmethod
    def _truncate_at_boundary(text: str, max_len: int = 100) -> str:
        """
        Truncate text at nearest sentence boundary within max_len.

        Prefers Chinese sentence endings (。！？), then Western (.!?),
        then last space. Appends ellipsis if truncated.
        """
        if len(text) <= max_len:
            return text

        segment = text[:max_len]

        # Find last sentence boundary (prefer CJK punctuation)
        for sep in ["。", "！", "？", ".", "!", "?"]:
            idx = segment.rfind(sep)
            if idx > max_len // 3:
                return segment[: idx + 1]

        # Fall back to last space
        space_idx = segment.rfind(" ")
        if space_idx > max_len // 3:
            return segment[:space_idx] + "..."

        return segment[: max_len - 3] + "..."


def _extract_session_metadata(pipeline_result) -> Dict[str, Any]:
    """Extract meeting session summary from PipelineResult for cloud reply.

    Pulls session_id, dispatch outcomes, and completion status from the
    pipeline result returned by ChatOrchestratorService.run_background_chat.
    Returns empty dict when pipeline_result is None (non-meeting flows).
    """
    meta: Dict[str, Any] = {}
    if not pipeline_result:
        return meta

    if getattr(pipeline_result, "meeting_session_id", None):
        meta["session_id"] = pipeline_result.meeting_session_id

    if getattr(pipeline_result, "dispatch_result", None):
        dr = pipeline_result.dispatch_result
        meta["dispatch_summary"] = {
            "total_phases": dr.get("total", 0),
            "succeeded": dr.get("succeeded", 0),
            "failed": dr.get("failed", 0),
            "skipped": dr.get("skipped", 0),
            "workspaces_touched": list(dr.get("workspaces", [])),
        }

    if getattr(pipeline_result, "completion_status", None):
        meta["completion_status"] = pipeline_result.completion_status

    if getattr(pipeline_result, "task_ir_id", None):
        meta["task_ir_id"] = pipeline_result.task_ir_id

    return meta


def _format_dispatch_summary(meta: Dict[str, Any]) -> str:
    """Format session dispatch summary for LINE display.

    Appends a human-readable execution summary block to the AI reply text.
    Uses emoji and Unicode box-drawing for readability on LINE.
    """
    ds = meta.get("dispatch_summary")
    if not ds:
        return ""

    lines = ["\n\n──── 執行摘要 ────"]
    total = ds.get("total_phases", 0)
    ok = ds.get("succeeded", 0)
    fail = ds.get("failed", 0)
    skip = ds.get("skipped", 0)
    lines.append(f"📊 任務: {ok}/{total} 成功")
    if fail:
        lines.append(f"❌ 失敗: {fail}")
    if skip:
        lines.append(f"⏭️ 跳過: {skip}")
    ws = ds.get("workspaces_touched", [])
    if ws:
        lines.append(f"🏠 工作區: {', '.join(ws[:3])}")
    status = meta.get("completion_status")
    if status:
        lines.append(f"📋 狀態: {status}")
    return "\n".join(lines)
