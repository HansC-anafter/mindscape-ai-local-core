"""Server-only handoff from a live media reservation to the host receiver."""

from __future__ import annotations

import asyncio
import os
from typing import Any, cast

from backend.app.models.media_transport import (
    LiveMediaSessionDescriptor,
    LiveMediaReceiverStateName,
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


RECEIVER_CLOSEOUT_WAIT_SECONDS = 75.0
RECEIVER_STATUS_POLL_INTERVAL_SECONDS = 0.5
RECEIVER_START_WAIT_MILLISECONDS = 30000
RECEIVER_START_RECOVERY_WAIT_MILLISECONDS = 5000
RECEIVER_TERMINAL_STATUSES = {"completed", "failed", "expired", "not_found"}
RECEIVER_ACTIVE_STARTUP_STATES = {
    "starting",
    "waiting_source",
    "receiving",
    "analyzing",
    "degraded",
}
RECEIVER_STATES = {
    "starting",
    "waiting_source",
    "receiving",
    "analyzing",
    "degraded",
    "stopping",
    "completed",
    "failed",
    "expired",
}


def _host_api_base() -> str:
    return os.getenv(
        "LOCAL_CORE_HOST_API_BASE",
        "http://127.0.0.1:8200",
    ).rstrip("/")


def _safe_status(result: dict[str, Any]) -> dict[str, Any]:
    forbidden = {"access_token", "append_owner_id", "receiver_token"}
    if forbidden.intersection(result):
        raise LiveMediaReceiverControlError("receiver_control_returned_secret")
    safe = dict(result)
    safe.pop("receiver_identity", None)
    return safe


def _receiver_state(value: Any) -> LiveMediaReceiverStateName:
    state = str(value or "").strip()
    if state not in RECEIVER_STATES:
        raise LiveMediaReceiverControlError("live_media_receiver_state_invalid")
    return cast(LiveMediaReceiverStateName, state)


def _is_exact_active_receiver_status(
    result: dict[str, Any],
    *,
    media_session_id: str,
    receiver_identity: str,
) -> bool:
    return (
        result.get("status") == "active"
        and str(result.get("media_session_id") or "") == media_session_id
        and str(result.get("receiver_identity") or "") == receiver_identity
        and str(result.get("state") or "") in RECEIVER_ACTIVE_STARTUP_STATES
    )


def _project_started_receiver(
    *,
    media_service: LiveMediaSessionService,
    media_session_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    status = _safe_status(result)
    if status.get("status") != "active":
        raise LiveMediaReceiverControlError("live_media_receiver_not_active")
    media_service.mark_receiver_started(media_session_id)
    media_service.update_receiver_state(
        media_session_id,
        _receiver_state(status.get("state")),
        reason=str(status.get("reason") or "").strip() or None,
    )
    return status


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
        try:
            result = await call_capture_relay_arguments(
                {
                    "action": "receiver_start",
                    "timeout_ms": RECEIVER_START_WAIT_MILLISECONDS,
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
                timeout_ms=RECEIVER_START_WAIT_MILLISECONDS,
            )
        except CaptureRelayUnavailable as start_error:
            try:
                recovered = await call_capture_relay_arguments(
                    {
                        "action": "receiver_status",
                        "media_session_id": media_session_id,
                    },
                    timeout_ms=RECEIVER_START_RECOVERY_WAIT_MILLISECONDS,
                )
            except CaptureRelayUnavailable:
                raise start_error
            if not _is_exact_active_receiver_status(
                recovered,
                media_session_id=media_session_id,
                receiver_identity=access.binding.receiver_identity,
            ):
                raise start_error
            result = recovered
        return _project_started_receiver(
            media_service=media_service,
            media_session_id=media_session_id,
            result=result,
        )
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
        deadline = asyncio.get_running_loop().time() + RECEIVER_CLOSEOUT_WAIT_SECONDS
        while status.get("status") not in RECEIVER_TERMINAL_STATUSES:
            if status.get("status") not in {"active", "stopping"}:
                raise LiveMediaReceiverControlError(
                    "live_media_receiver_stop_not_confirmed"
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise LiveMediaReceiverControlError(
                    "live_media_receiver_stop_not_confirmed"
                )
            await asyncio.sleep(RECEIVER_STATUS_POLL_INTERVAL_SECONDS)
            status = _safe_status(
                await call_capture_relay_arguments(
                    {
                        "action": "receiver_status",
                        "media_session_id": media_session_id,
                    },
                    timeout_ms=5000,
                )
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
