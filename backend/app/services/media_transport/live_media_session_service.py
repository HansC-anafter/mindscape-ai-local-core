"""Canonical facade for authorized live media session control."""

from __future__ import annotations

from functools import lru_cache

from backend.app.models.device_binding import DeviceSessionEntry
from backend.app.models.media_transport import (
    CreateLiveMediaSessionRequest,
    LiveMediaReceiverAccess,
    LiveMediaSessionAccess,
    LiveMediaSessionDescriptor,
)

from .live_media_config import LiveMediaConfig, LiveMediaConfigError
from .live_media_session_registry import (
    LiveMediaSessionRegistry,
    LiveMediaSessionRegistryError,
)
from .live_media_token_service import LiveMediaTokenError, LiveMediaTokenService


class LiveMediaSessionServiceError(RuntimeError):
    """Stable facade error suitable for route translation."""

    def __init__(self, reason: str, *, status_code: int = 400) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class LiveMediaSessionService:
    """Create one media path and issue credentials for its exact actions."""

    def __init__(
        self,
        config: LiveMediaConfig,
        *,
        registry: LiveMediaSessionRegistry | None = None,
        token_service: LiveMediaTokenService | None = None,
    ) -> None:
        self._registry = registry or LiveMediaSessionRegistry(config)
        self._token_service = token_service or LiveMediaTokenService(config)

    def create(
        self,
        *,
        device_session: DeviceSessionEntry,
        request: CreateLiveMediaSessionRequest,
    ) -> LiveMediaSessionAccess:
        if request.source_kind not in device_session.source_types:
            raise LiveMediaSessionServiceError(
                "live_media_source_kind_not_declared",
                status_code=409,
            )
        try:
            descriptor = self._registry.create(
                workspace_id=device_session.workspace_id,
                device_session_id=device_session.session_id,
                request=request,
            )
            return self._access(descriptor)
        except LiveMediaSessionRegistryError as exc:
            raise LiveMediaSessionServiceError(
                exc.reason,
                status_code=exc.status_code,
            ) from exc

    def get_active(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
    ) -> LiveMediaSessionDescriptor:
        try:
            return self._registry.get_active(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
            )
        except LiveMediaSessionRegistryError as exc:
            raise LiveMediaSessionServiceError(
                exc.reason,
                status_code=exc.status_code,
            ) from exc

    def refresh_access(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
    ) -> LiveMediaSessionAccess:
        try:
            descriptor = self._registry.get_active(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            )
            return self._access(descriptor)
        except LiveMediaSessionRegistryError as exc:
            raise LiveMediaSessionServiceError(
                exc.reason,
                status_code=exc.status_code,
            ) from exc

    def stop(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        reason: str = "stopped_by_client",
    ) -> LiveMediaSessionDescriptor:
        try:
            return self._registry.stop(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                reason=reason,
            )
        except LiveMediaSessionRegistryError as exc:
            raise LiveMediaSessionServiceError(
                exc.reason,
                status_code=exc.status_code,
            ) from exc

    def receiver_access(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
    ) -> LiveMediaReceiverAccess:
        try:
            descriptor = self._registry.get_active(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            )
            binding = self._registry.get_receiver_binding(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            )
            return LiveMediaReceiverAccess(
                session=descriptor,
                binding=binding,
                receiver_token=self._token_service.issue_receiver_token(descriptor),
            )
        except LiveMediaSessionRegistryError as exc:
            raise LiveMediaSessionServiceError(
                exc.reason,
                status_code=exc.status_code,
            ) from exc
        except LiveMediaTokenError as exc:
            raise LiveMediaSessionServiceError(str(exc), status_code=503) from exc

    def mark_receiver_started(self, media_session_id: str) -> None:
        try:
            self._registry.mark_receiver_started(media_session_id)
        except LiveMediaSessionRegistryError as exc:
            raise LiveMediaSessionServiceError(
                exc.reason,
                status_code=exc.status_code,
            ) from exc

    def receiver_started(self, media_session_id: str) -> bool:
        return self._registry.receiver_started(media_session_id)

    def _access(
        self,
        descriptor: LiveMediaSessionDescriptor,
    ) -> LiveMediaSessionAccess:
        try:
            tokens = self._token_service.issue_session_tokens(descriptor)
        except LiveMediaTokenError as exc:
            raise LiveMediaSessionServiceError(str(exc), status_code=503) from exc
        return LiveMediaSessionAccess(session=descriptor, tokens=tokens)


@lru_cache(maxsize=1)
def get_live_media_session_service() -> LiveMediaSessionService:
    try:
        config = LiveMediaConfig.from_env()
        return LiveMediaSessionService(config)
    except (LiveMediaConfigError, LiveMediaTokenError) as exc:
        raise LiveMediaSessionServiceError(str(exc), status_code=503) from exc


__all__ = [
    "LiveMediaSessionService",
    "LiveMediaSessionServiceError",
    "get_live_media_session_service",
]
