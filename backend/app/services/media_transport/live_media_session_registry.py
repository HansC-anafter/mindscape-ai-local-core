"""Bounded process-local registry for live media session control state."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Callable

from backend.app.models.media_transport import (
    CreateLiveMediaSessionRequest,
    LiveMediaReceiverBinding,
    LiveMediaSessionDescriptor,
    LiveMediaSessionEndpoints,
    LiveMediaReceiverStateName,
)

from .live_media_config import LiveMediaConfig


MAX_ACTIVE_MEDIA_SESSIONS_PER_WORKSPACE = 3
RECEIVER_MEDIA_STATE = {
    "starting": "waiting_for_publisher",
    "waiting_source": "waiting_for_publisher",
    "receiving": "publishing",
    "analyzing": "ready",
    "degraded": "degraded",
    "stopping": "ready",
    "completed": "ready",
    "failed": "degraded",
    "expired": "expired",
}


class LiveMediaSessionRegistryError(RuntimeError):
    """Registry error with a stable API reason and status."""

    def __init__(self, reason: str, *, status_code: int = 400) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class LiveMediaSessionRegistry:
    """Own the one active media path for each bound device session."""

    def __init__(
        self,
        config: LiveMediaConfig,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._now = now
        self._sessions: dict[str, LiveMediaSessionDescriptor] = {}
        self._device_sessions: dict[tuple[str, str], str] = {}
        self._receiver_bindings: dict[str, LiveMediaReceiverBinding] = {}
        self._started_receivers: set[str] = set()
        self._lock = threading.RLock()

    def create(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        request: CreateLiveMediaSessionRequest,
    ) -> LiveMediaSessionDescriptor:
        with self._lock:
            self.cleanup_expired()
            device_key = (workspace_id, device_session_id)
            existing_id = self._device_sessions.get(device_key)
            if existing_id:
                existing = self._sessions.get(existing_id)
                if existing is not None:
                    if (
                        existing.source_kind != request.source_kind
                        or existing.relay_profile != request.relay_profile
                        or existing.analysis_reserved != request.analysis_reserved
                        or existing.capabilities != request.capabilities
                    ):
                        raise LiveMediaSessionRegistryError(
                            "live_media_session_contract_conflict",
                            status_code=409,
                        )
                    return existing.model_copy(deep=True)

            active = self.list_active(workspace_id=workspace_id)
            if len(active) >= MAX_ACTIVE_MEDIA_SESSIONS_PER_WORKSPACE:
                raise LiveMediaSessionRegistryError(
                    "active_live_media_session_limit_reached",
                    status_code=409,
                )
            if request.analysis_reserved and any(
                session.analysis_reserved for session in active
            ):
                raise LiveMediaSessionRegistryError(
                    "workspace_analysis_session_already_reserved",
                    status_code=409,
                )

            now_epoch = self._now()
            media_session_id = f"lms_{secrets.token_hex(8)}"
            stream_path = f"live/{secrets.token_urlsafe(24)}"
            descriptor = LiveMediaSessionDescriptor(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                stream_path=stream_path,
                source_kind=request.source_kind,
                relay_profile=request.relay_profile,
                capabilities=request.capabilities,
                analysis_reserved=request.analysis_reserved,
                state="waiting_for_publisher",
                endpoints=self._endpoints(stream_path),
                receiver_descriptor_ref=f"live-media-receiver:{media_session_id}",
                created_at_epoch=now_epoch,
                updated_at_epoch=now_epoch,
                expires_at_epoch=now_epoch + self._config.session_ttl_seconds,
            )
            self._sessions[media_session_id] = descriptor
            self._device_sessions[device_key] = media_session_id
            self._receiver_bindings[media_session_id] = LiveMediaReceiverBinding(
                receiver_identity=f"receiver_{secrets.token_urlsafe(18)}",
                append_owner_id=f"append_{secrets.token_urlsafe(24)}",
            )
            return descriptor.model_copy(deep=True)

    def get_active(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str | None = None,
    ) -> LiveMediaSessionDescriptor:
        with self._lock:
            self.cleanup_expired()
            resolved_id = media_session_id or self._device_sessions.get(
                (workspace_id, device_session_id)
            )
            descriptor = self._sessions.get(resolved_id or "")
            if (
                descriptor is None
                or descriptor.workspace_id != workspace_id
                or descriptor.device_session_id != device_session_id
            ):
                raise LiveMediaSessionRegistryError(
                    "live_media_session_not_found",
                    status_code=404,
                )
            return descriptor.model_copy(deep=True)

    def get_receiver_binding(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
    ) -> LiveMediaReceiverBinding:
        with self._lock:
            self.get_active(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            )
            binding = self._receiver_bindings.get(media_session_id)
            if binding is None:
                raise LiveMediaSessionRegistryError(
                    "live_media_receiver_binding_not_found",
                    status_code=404,
                )
            return binding.model_copy(deep=True)

    def mark_receiver_started(self, media_session_id: str) -> None:
        with self._lock:
            if media_session_id not in self._receiver_bindings:
                raise LiveMediaSessionRegistryError(
                    "live_media_receiver_binding_not_found",
                    status_code=404,
                )
            self._started_receivers.add(media_session_id)

    def receiver_started(self, media_session_id: str) -> bool:
        with self._lock:
            return media_session_id in self._started_receivers

    def update_receiver_state(
        self,
        media_session_id: str,
        state: LiveMediaReceiverStateName,
        *,
        reason: str | None = None,
    ) -> LiveMediaSessionDescriptor:
        with self._lock:
            descriptor = self._sessions.get(media_session_id)
            if descriptor is None:
                raise LiveMediaSessionRegistryError(
                    "live_media_session_not_found",
                    status_code=404,
                )
            projected_state = RECEIVER_MEDIA_STATE[state]
            terminal_reason = descriptor.terminal_reason
            if state in {"failed", "expired"}:
                terminal_reason = reason or state
            updated = descriptor.model_copy(
                update={
                    "state": projected_state,
                    "updated_at_epoch": self._now(),
                    "terminal_reason": terminal_reason,
                }
            )
            self._sessions[media_session_id] = updated
            return updated.model_copy(deep=True)

    def stop(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        reason: str = "stopped_by_client",
    ) -> LiveMediaSessionDescriptor:
        with self._lock:
            descriptor = self.get_active(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            )
            descriptor.state = "stopped"
            descriptor.terminal_reason = reason
            descriptor.updated_at_epoch = self._now()
            self._sessions.pop(media_session_id, None)
            self._receiver_bindings.pop(media_session_id, None)
            self._started_receivers.discard(media_session_id)
            self._device_sessions.pop((workspace_id, device_session_id), None)
            return descriptor

    def list_active(self, *, workspace_id: str) -> list[LiveMediaSessionDescriptor]:
        with self._lock:
            self.cleanup_expired()
            return [
                session.model_copy(deep=True)
                for session in self._sessions.values()
                if session.workspace_id == workspace_id
            ]

    def cleanup_expired(self) -> int:
        with self._lock:
            now_epoch = self._now()
            expired_ids = [
                media_session_id
                for media_session_id, descriptor in self._sessions.items()
                if descriptor.expires_at_epoch <= now_epoch
            ]
            for media_session_id in expired_ids:
                descriptor = self._sessions.pop(media_session_id)
                self._receiver_bindings.pop(media_session_id, None)
                self._started_receivers.discard(media_session_id)
                self._device_sessions.pop(
                    (descriptor.workspace_id, descriptor.device_session_id),
                    None,
                )
            return len(expired_ids)

    def _endpoints(self, stream_path: str) -> LiveMediaSessionEndpoints:
        return LiveMediaSessionEndpoints(
            whip_publish_url=(
                f"{self._config.public_webrtc_origin}/{stream_path}/whip"
            ),
            whep_preview_url=(
                f"{self._config.public_webrtc_origin}/{stream_path}/whep"
            ),
            rtmps_publish_url=(
                f"{self._config.public_rtmps_origin}/{stream_path}"
            ),
            rtsps_receiver_url=(
                f"{self._config.receiver_rtsps_origin}/{stream_path}"
            ),
        )


__all__ = [
    "LiveMediaSessionRegistry",
    "LiveMediaSessionRegistryError",
    "MAX_ACTIVE_MEDIA_SESSIONS_PER_WORKSPACE",
    "RECEIVER_MEDIA_STATE",
]
