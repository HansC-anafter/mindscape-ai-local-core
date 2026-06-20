"""Cloud connector messaging handler facade."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from websockets.client import WebSocketClientProtocol

from .messaging_assets import (
    ASSET_UPLOAD_BASE_ENV_KEYS,
    ASSET_UPLOAD_TOKEN_ENV_KEYS,
    append_unique_text as _append_unique_text_impl,
    as_mapping as _as_mapping_impl,
    asset_candidate_from_model as _asset_candidate_from_model_impl,
    asset_candidate_from_payload as _asset_candidate_from_payload_impl,
    candidate_file_path as _candidate_file_path_impl,
    candidate_public_url as _candidate_public_url_impl,
    clean_text as _clean_text_impl,
    collect_asset_candidates as _collect_asset_candidates_impl,
    collect_execution_ids as _collect_execution_ids_impl,
    dedupe_asset_candidates as _dedupe_asset_candidates_impl,
    escape_markdown_label as _escape_markdown_label_impl,
    format_page_assets_md as _format_page_assets_md_impl,
    is_public_url as _is_public_url_impl,
    materialize_page_assets as _materialize_page_assets_impl,
    resolve_asset_upload_base as _resolve_asset_upload_base_impl,
    resolve_asset_upload_token as _resolve_asset_upload_token_impl,
    upload_page_asset as _upload_page_asset_impl,
)
from .messaging_meeting_details import (
    build_meeting_assets_md as _build_meeting_assets_md_impl,
    build_meeting_detail_md as _build_meeting_detail_md_impl,
)
from .messaging_reply_summary import (
    extract_session_metadata as _extract_session_metadata_impl,
    format_dispatch_summary as _format_dispatch_summary_impl,
    generate_reply_summary as _generate_reply_summary_impl,
    truncate_at_boundary as _truncate_at_boundary_impl,
)
from .messaging_workspace_dispatch import (
    dispatch_to_workspace as _dispatch_to_workspace_impl,
    resolve_workspace_id as _resolve_workspace_id_impl,
    send_reply as _send_reply_impl,
    utc_now as _utc_now_impl,
)

logger = logging.getLogger(__name__)

_ASSET_UPLOAD_BASE_ENV_KEYS = ASSET_UPLOAD_BASE_ENV_KEYS
_ASSET_UPLOAD_TOKEN_ENV_KEYS = ASSET_UPLOAD_TOKEN_ENV_KEYS


def _utc_now():
    """Return timezone-aware UTC now."""
    return _utc_now_impl()


def _clean_text(value: Any) -> Optional[str]:
    return _clean_text_impl(value)


def _as_mapping(value: Any) -> Dict[str, Any]:
    return _as_mapping_impl(value)


def _append_unique_text(values: List[str], value: Optional[str]) -> None:
    _append_unique_text_impl(values, value)


def _is_public_url(value: Any) -> bool:
    return _is_public_url_impl(value)


def _resolve_asset_upload_base() -> Optional[str]:
    return _resolve_asset_upload_base_impl()


def _resolve_asset_upload_token() -> Optional[str]:
    return _resolve_asset_upload_token_impl()


def _candidate_file_path(payload: Dict[str, Any]) -> Optional[str]:
    return _candidate_file_path_impl(payload)


def _candidate_public_url(payload: Dict[str, Any]) -> Optional[str]:
    return _candidate_public_url_impl(payload)


def _asset_candidate_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _asset_candidate_from_payload_impl(payload)


def _collect_asset_candidates(value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
    return _collect_asset_candidates_impl(value, depth=depth)


def _collect_execution_ids(value: Any, *, depth: int = 0) -> List[str]:
    return _collect_execution_ids_impl(value, depth=depth)


def _dedupe_asset_candidates(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _dedupe_asset_candidates_impl(candidates)


def _asset_candidate_from_model(artifact: Any) -> Optional[Dict[str, Any]]:
    return _asset_candidate_from_model_impl(artifact)


async def _upload_page_asset(
    file_path: Path,
    *,
    workspace_id: str,
) -> Optional[str]:
    return await _upload_page_asset_impl(file_path, workspace_id=workspace_id)


async def _materialize_page_assets(
    candidates: List[Dict[str, Any]],
    *,
    workspace_id: str,
) -> List[Dict[str, Any]]:
    return await _materialize_page_assets_impl(
        candidates,
        workspace_id=workspace_id,
        upload_func=_upload_page_asset,
    )


def _escape_markdown_label(value: str) -> str:
    return _escape_markdown_label_impl(value)


def _format_page_assets_md(assets: List[Dict[str, Any]]) -> str:
    return _format_page_assets_md_impl(assets)


def _extract_session_metadata(pipeline_result) -> Dict[str, Any]:
    return _extract_session_metadata_impl(pipeline_result)


def _format_dispatch_summary(meta: Dict[str, Any]) -> str:
    return _format_dispatch_summary_impl(meta)


class MessagingHandler:
    """Route cloud provider messaging events to workspace chat."""

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
            workspace_id: Default workspace ID
        """
        self.websocket = websocket
        self.device_id = device_id
        self.workspace_id = workspace_id
        self._active_sessions: Dict[str, asyncio.Task] = {}
        self._processed_requests: Dict[str, float] = {}
        self._dedup_ttl_seconds = 120
        self._latest_workspace_request: Dict[str, str] = {}

    def _is_duplicate_request(self, request_id: str) -> bool:
        """Check if request_id was already processed or is in-progress."""
        now = time.time()
        expired = [
            request_key
            for request_key, timestamp in self._processed_requests.items()
            if now - timestamp > self._dedup_ttl_seconds
        ]
        for request_key in expired:
            del self._processed_requests[request_key]

        return request_id in self._processed_requests

    async def handle(self, payload: Dict[str, Any]) -> None:
        """Handle an incoming messaging event from the cloud provider."""
        channel = payload.get("channel", "unknown")
        event_type = payload.get("event_type", "unknown")
        request_id = payload.get("request_id", f"msg_{uuid.uuid4().hex[:16]}")

        logger.info(
            f"[MessagingHandler] Received {channel}/{event_type} "
            f"request_id={request_id}"
        )

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

        task = asyncio.create_task(self._dispatch_to_workspace(request_id, payload, text))
        self._active_sessions[request_id] = task

    async def _resolve_workspace_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Resolve workspace_id from channel binding or fallbacks."""
        return await _resolve_workspace_id_impl(self, payload)

    async def _dispatch_to_workspace(
        self,
        request_id: str,
        original_payload: Dict[str, Any],
        message_text: str,
    ) -> None:
        """Dispatch a messaging request to workspace chat."""
        await _dispatch_to_workspace_impl(
            self,
            request_id,
            original_payload,
            message_text,
        )

    async def _build_meeting_detail_md(
        self,
        store,
        workspace_id: str,
        pipeline_result,
    ) -> str:
        """Build Markdown with full meeting discussion, actions, and stats."""
        return await _build_meeting_detail_md_impl(
            self,
            store,
            workspace_id,
            pipeline_result,
        )

    async def _build_meeting_assets_md(
        self,
        store,
        workspace_id: str,
        pipeline_result,
    ) -> str:
        """Build a public-result-page section for meeting artifacts."""
        return await _build_meeting_assets_md_impl(
            self,
            store,
            workspace_id,
            pipeline_result,
        )

    async def _send_reply(
        self,
        request_id: str,
        original_payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Send a messaging reply back to the cloud provider via WebSocket."""
        await _send_reply_impl(self, request_id, original_payload, result)

    async def _generate_reply_summary(
        self,
        reply_text: str,
        *,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> str:
        """Generate a concise summary for rich-card display."""
        return await _generate_reply_summary_impl(
            reply_text,
            workspace_id=workspace_id,
            profile_id=profile_id,
        )

    @staticmethod
    def _truncate_at_boundary(text: str, max_len: int = 100) -> str:
        """Truncate text at the nearest sentence boundary within max_len."""
        return _truncate_at_boundary_impl(text, max_len=max_len)
