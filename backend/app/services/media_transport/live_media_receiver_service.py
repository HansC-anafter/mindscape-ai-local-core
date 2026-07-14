"""Server-only handoff from a live media reservation to the host receiver."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from backend.app.models.media_transport import (
    LiveMediaSessionDescriptor,
    StartLiveMediaReceiverRequest,
)
from backend.app.services.host_services.capture_relay_proxy import (
    CaptureRelayUnavailable,
    call_capture_relay_arguments,
)

from .live_media_session_service import (
    LiveMediaSessionService,
    LiveMediaSessionServiceError,
)
from .motion_reference_profile_artifact import (
    ArtifactLookup,
    MotionReferenceProfileArtifactError,
    resolve_selected_motion_reference_profile,
)


class LiveMediaReceiverControlError(RuntimeError):
    """Stable receiver-control failure suitable for route translation."""

    def __init__(self, reason: str, *, status_code: int = 503) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def _host_api_base() -> str:
    return os.getenv(
        "LOCAL_CORE_HOST_API_BASE",
        "http://127.0.0.1:8200",
    ).rstrip("/")


def _safe_status(result: dict[str, Any]) -> dict[str, Any]:
    forbidden = {"access_token", "append_owner_id", "receiver_token"}
    if forbidden.intersection(result):
        raise LiveMediaReceiverControlError("receiver_control_returned_secret")
    return result


async def start_live_media_receiver(
    *,
    media_service: LiveMediaSessionService,
    workspace_id: str,
    device_session_id: str,
    media_session_id: str,
    request: StartLiveMediaReceiverRequest,
    artifact_store: ArtifactLookup | None = None,
) -> dict[str, Any]:
    try:
        motion_reference_profile = None
        if request.motion_reference_profile_artifact_id or (
            request.coach_pack == "yogacoach" and request.reference_url
        ):
            if artifact_store is None:
                raise LiveMediaReceiverControlError(
                    "motion_reference_profile_artifact_store_unavailable"
                )
            motion_reference_profile = await asyncio.to_thread(
                resolve_selected_motion_reference_profile,
                artifact_store=artifact_store,
                workspace_id=workspace_id,
                artifact_id=request.motion_reference_profile_artifact_id,
                source_ref=request.reference_url,
            )
        access = media_service.receiver_access(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        result = await call_capture_relay_arguments(
            {
                "action": "receiver_start",
                "timeout_ms": 10000,
                "receiver_descriptor": {
                    "schema_version": "live_media_receiver.v1",
                    "workspace_id": workspace_id,
                    "device_session_id": device_session_id,
                    "media_session_id": media_session_id,
                    "live_motion_session_id": request.live_motion_session_id,
                    "meeting_session_id": request.meeting_session_id,
                    "practice_session_id": request.practice_session_id,
                    "receiver_identity": access.binding.receiver_identity,
                    "append_owner_id": access.binding.append_owner_id,
                    "source_kind": access.session.source_kind,
                    "transport_kind": "rtsps",
                    "input_url": access.session.endpoints.rtsps_receiver_url,
                    "access_token": access.receiver_token,
                    "expires_at_epoch": access.session.expires_at_epoch,
                    "api_base": _host_api_base(),
                    "coach_pack": request.coach_pack,
                    "practice_mode": request.practice_mode,
                    "reference_url": request.reference_url,
                    "motion_reference_profile": (
                        motion_reference_profile.receiver_ref()
                        if motion_reference_profile is not None
                        else None
                    ),
                    "user_goal": request.user_goal,
                    "expected_duration_ms": request.expected_duration_ms,
                },
            },
            timeout_ms=10000,
        )
        status = _safe_status(result)
        if status.get("status") != "active":
            raise LiveMediaReceiverControlError("live_media_receiver_not_active")
        media_service.mark_receiver_started(media_session_id)
        return status
    except LiveMediaSessionServiceError as exc:
        raise LiveMediaReceiverControlError(
            exc.reason,
            status_code=exc.status_code,
        ) from exc
    except MotionReferenceProfileArtifactError as exc:
        raise LiveMediaReceiverControlError(
            exc.reason,
            status_code=exc.status_code,
        ) from exc
    except CaptureRelayUnavailable as exc:
        raise LiveMediaReceiverControlError(exc.reason) from exc


async def stop_live_media_receiver(
    *,
    media_service: LiveMediaSessionService,
    workspace_id: str,
    device_session_id: str,
    media_session_id: str,
) -> dict[str, Any]:
    try:
        access = media_service.receiver_access(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        result = await call_capture_relay_arguments(
            {
                "action": "receiver_stop",
                "timeout_ms": 10000,
                "media_session_id": media_session_id,
                "receiver_identity": access.binding.receiver_identity,
            },
            timeout_ms=10000,
        )
        status = _safe_status(result)
        if status.get("status") not in {
            "completed",
            "failed",
            "expired",
            "not_found",
        }:
            raise LiveMediaReceiverControlError(
                "live_media_receiver_stop_not_confirmed"
            )
        return status
    except LiveMediaSessionServiceError as exc:
        raise LiveMediaReceiverControlError(
            exc.reason,
            status_code=exc.status_code,
        ) from exc
    except CaptureRelayUnavailable as exc:
        raise LiveMediaReceiverControlError(exc.reason) from exc


async def terminate_live_media_session(
    *,
    media_service: LiveMediaSessionService,
    workspace_id: str,
    device_session_id: str,
    media_session_id: str,
    reason: str,
) -> LiveMediaSessionDescriptor:
    """Stop the host receiver before releasing its server-owned identity."""

    if media_service.receiver_started(media_session_id):
        await stop_live_media_receiver(
            media_service=media_service,
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
    return media_service.stop(
        workspace_id=workspace_id,
        device_session_id=device_session_id,
        media_session_id=media_session_id,
        reason=reason,
    )


__all__ = [
    "LiveMediaReceiverControlError",
    "start_live_media_receiver",
    "stop_live_media_receiver",
    "terminate_live_media_session",
]
