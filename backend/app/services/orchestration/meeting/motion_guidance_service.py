"""Bounded live guidance for motion practice sessions."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.models.meeting_motion_guidance import (
    MeetingMotionGuidanceClientMessage,
    MeetingMotionGuidanceEvent,
)


FORBIDDEN_MOTION_GUIDANCE_KEYS = frozenset(
    {
        "raw_frame",
        "raw_frames",
        "raw_video",
        "video_base64",
        "frame_base64",
        "frames",
        "keypoints",
        "landmarks",
        "pose_landmarks",
    }
)

DEFAULT_MIN_SPEAKABLE_INTERVAL_SECONDS = 3.0
DEFAULT_DUPLICATE_SUPPRESSION_SECONDS = 15.0
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5


class MotionGuidanceError(Exception):
    """Structured recoverable or terminal guidance error."""

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        recoverable: bool = True,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = message
        self.recoverable = recoverable


@dataclass
class MotionGuidanceSession:
    """In-memory state for one active guidance WebSocket."""

    workspace_id: str
    meeting_id: str
    practice_session_id: str
    state: str = "idle"
    cue_sequence: int = 0
    last_speakable_epoch: float | None = None
    last_cue_epoch_by_key: dict[str, float] = field(default_factory=dict)


class MeetingMotionGuidanceService:
    """Generate bounded cue events from compact motion analysis events."""

    def __init__(
        self,
        *,
        min_speakable_interval_seconds: float = DEFAULT_MIN_SPEAKABLE_INTERVAL_SECONDS,
        duplicate_suppression_seconds: float = DEFAULT_DUPLICATE_SUPPRESSION_SECONDS,
        low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.min_speakable_interval_seconds = min_speakable_interval_seconds
        self.duplicate_suppression_seconds = duplicate_suppression_seconds
        self.low_confidence_threshold = low_confidence_threshold

    def handle_message(
        self,
        *,
        session: MotionGuidanceSession,
        message: MeetingMotionGuidanceClientMessage,
        now_epoch: float | None = None,
    ) -> MeetingMotionGuidanceEvent | None:
        """Return one event for one client message without persistence."""

        now = now_epoch if now_epoch is not None else time.time()
        self._reject_raw_payload(message)

        if message.type == "session_start":
            session.state = "active"
            return self._event(
                session=session,
                event_type="session_ready",
                state="active",
                event_id=message.event_id,
            )

        if message.type == "ack":
            return None

        if message.type == "interrupt":
            session.state = "interrupted"
            return self._event(
                session=session,
                event_type="interrupted",
                state="interrupted",
                event_id=message.event_id,
            )

        if message.type == "session_close":
            session.state = "closed"
            return self._event(
                session=session,
                event_type="session_closed",
                state="closed",
                event_id=message.event_id,
            )

        if message.type in {"motion_window", "rollup_delta", "practice_state"}:
            session.state = "active"
            return self._guidance_event(session=session, message=message, now_epoch=now)

        raise MotionGuidanceError(
            reason="unsupported_message_type",
            message="Unsupported motion guidance message type.",
        )

    def _guidance_event(
        self,
        *,
        session: MotionGuidanceSession,
        message: MeetingMotionGuidanceClientMessage,
        now_epoch: float,
    ) -> MeetingMotionGuidanceEvent:
        confidence = self._extract_confidence(message)
        if confidence is not None and confidence < self.low_confidence_threshold:
            return self._cue_event(
                session=session,
                message=message,
                cue_key="low_confidence",
                cue_text="Hold steady in camera view before applying movement corrections.",
                cue_priority="warning",
                speakable=False,
                now_epoch=now_epoch,
            )

        finding = self._first_finding(message)
        if not finding:
            return self._event(
                session=session,
                event_type="guidance_suppressed",
                state="active",
                event_id=message.event_id,
                reason="no_actionable_cue",
                message="No actionable compact motion finding was provided.",
                recoverable=True,
                motion_window_ref=message.motion_window_ref,
                rollup_ref=message.rollup_ref,
                command_ref=message.command_ref,
            )

        cue_key = self._cue_key(finding)
        last_duplicate_epoch = session.last_cue_epoch_by_key.get(cue_key)
        if (
            last_duplicate_epoch is not None
            and now_epoch - last_duplicate_epoch < self.duplicate_suppression_seconds
        ):
            return self._event(
                session=session,
                event_type="guidance_suppressed",
                state="active",
                event_id=message.event_id,
                cue_key=cue_key,
                reason="duplicate_cue",
                message="Duplicate cue suppressed for the active practice session.",
                recoverable=True,
                throttle_until_epoch=last_duplicate_epoch
                + self.duplicate_suppression_seconds,
                motion_window_ref=message.motion_window_ref,
                rollup_ref=message.rollup_ref,
                command_ref=message.command_ref,
            )

        if (
            session.last_speakable_epoch is not None
            and now_epoch - session.last_speakable_epoch
            < self.min_speakable_interval_seconds
        ):
            return self._event(
                session=session,
                event_type="guidance_suppressed",
                state="active",
                event_id=message.event_id,
                cue_key=cue_key,
                reason="cue_throttled",
                message="Speakable cue suppressed by the practice session throttle.",
                recoverable=True,
                throttle_until_epoch=session.last_speakable_epoch
                + self.min_speakable_interval_seconds,
                motion_window_ref=message.motion_window_ref,
                rollup_ref=message.rollup_ref,
                command_ref=message.command_ref,
            )

        return self._cue_event(
            session=session,
            message=message,
            cue_key=cue_key,
            cue_text=finding[:260],
            cue_priority="correction",
            speakable=True,
            now_epoch=now_epoch,
        )

    def _cue_event(
        self,
        *,
        session: MotionGuidanceSession,
        message: MeetingMotionGuidanceClientMessage,
        cue_key: str,
        cue_text: str,
        cue_priority: str,
        speakable: bool,
        now_epoch: float,
    ) -> MeetingMotionGuidanceEvent:
        session.cue_sequence += 1
        session.last_cue_epoch_by_key[cue_key] = now_epoch
        if speakable:
            session.last_speakable_epoch = now_epoch
        return self._event(
            session=session,
            event_type="guidance_cue",
            state="active",
            event_id=message.event_id,
            cue_id=f"{session.practice_session_id}:cue:{session.cue_sequence}",
            cue_key=cue_key,
            cue_text=cue_text,
            cue_priority=cue_priority,
            speakable=speakable,
            motion_window_ref=message.motion_window_ref,
            rollup_ref=message.rollup_ref,
            command_ref=message.command_ref,
        )

    @staticmethod
    def _event(
        *,
        session: MotionGuidanceSession,
        event_type: str,
        state: str,
        **extra: Any,
    ) -> MeetingMotionGuidanceEvent:
        return MeetingMotionGuidanceEvent(
            type=event_type,
            workspace_id=session.workspace_id,
            meeting_id=session.meeting_id,
            practice_session_id=session.practice_session_id,
            state=state,
            **extra,
        )

    @staticmethod
    def _first_finding(message: MeetingMotionGuidanceClientMessage) -> str | None:
        for finding in [*message.top_findings, *message.findings]:
            if isinstance(finding, str) and finding.strip():
                return finding.strip()
        metadata_findings = message.metadata.get("top_findings") or message.metadata.get("findings")
        if isinstance(metadata_findings, list):
            for finding in metadata_findings:
                if isinstance(finding, str) and finding.strip():
                    return finding.strip()
        return None

    @staticmethod
    def _extract_confidence(message: MeetingMotionGuidanceClientMessage) -> float | None:
        for value in (
            message.confidence,
            message.mean_confidence,
            message.metadata.get("confidence"),
            message.metadata.get("mean_confidence"),
        ):
            if isinstance(value, (int, float)):
                return float(value)
        return None

    @staticmethod
    def _cue_key(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        return normalized[:80] or "motion_cue"

    @staticmethod
    def _reject_raw_payload(message: MeetingMotionGuidanceClientMessage) -> None:
        payload = message.model_dump(mode="json", exclude_none=True)
        forbidden = _find_forbidden_key(payload)
        if forbidden:
            raise MotionGuidanceError(
                reason="raw_motion_payload_rejected",
                message=f"Motion guidance accepts compact refs only; rejected key: {forbidden}.",
                recoverable=False,
            )


def _find_forbidden_key(value: Any, *, depth: int = 0) -> str | None:
    if depth > 8:
        return None
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_MOTION_GUIDANCE_KEYS:
                return key
            found = _find_forbidden_key(nested, depth=depth + 1)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_forbidden_key(nested, depth=depth + 1)
            if found:
                return found
    return None


__all__ = [
    "DEFAULT_DUPLICATE_SUPPRESSION_SECONDS",
    "DEFAULT_LOW_CONFIDENCE_THRESHOLD",
    "DEFAULT_MIN_SPEAKABLE_INTERVAL_SECONDS",
    "FORBIDDEN_MOTION_GUIDANCE_KEYS",
    "MeetingMotionGuidanceService",
    "MotionGuidanceError",
    "MotionGuidanceSession",
]
