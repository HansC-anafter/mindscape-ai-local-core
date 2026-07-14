"""Initial live-source acquisition under the receiver reconnect policy."""

from __future__ import annotations

from typing import Any, Callable

from .source_uri import public_input_uri


def acquire_initial_stream(
    args: Any,
    *,
    should_stop: Callable[[], bool],
    open_capture: Callable[[Any], Any],
    emit_event: Callable[[dict[str, Any]], None],
    transition_state: Callable[..., None],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[Any, Any, int] | None:
    """Wait for the first publisher frame until stop, retry limit, or session TTL."""

    wait_started_at = monotonic()
    reconnect_attempts = 0
    input_uri = public_input_uri(args.rtmp_url)
    while not should_stop():
        capture = open_capture(args)
        reason = "stream_not_open"
        if capture.isOpened():
            first_frame_ok, first_frame = capture.read()
            if first_frame_ok:
                return capture, first_frame, reconnect_attempts
            reason = "initial_frame_unavailable"
        emit_event(
            {
                "event": "stream_open_failed",
                "input_uri": input_uri,
                "reason": reason,
            }
        )
        capture.release()

        elapsed_sec = monotonic() - wait_started_at
        source_wait_timeout_sec = max(
            0.0,
            float(getattr(args, "source_wait_timeout_sec", 0.0) or 0.0),
        )
        attempts_exhausted = (
            args.stream_reconnect_max_attempts > 0
            and reconnect_attempts >= args.stream_reconnect_max_attempts
        )
        wait_expired = (
            source_wait_timeout_sec > 0
            and elapsed_sec >= source_wait_timeout_sec
        )
        if attempts_exhausted or wait_expired:
            emit_event(
                {
                    "event": "stream_reconnect_give_up",
                    "reason": reason,
                    "attempts": reconnect_attempts,
                    "elapsed_sec": round(elapsed_sec, 3),
                }
            )
            return None

        reconnect_attempts += 1
        emit_event(
            {
                "event": "stream_reconnect_started",
                "reason": reason,
                "attempt": reconnect_attempts,
                "elapsed_sec": round(elapsed_sec, 3),
            }
        )
        transition_state(args, "waiting_source", reason=reason)
        backoff_sec = max(0.0, args.stream_reconnect_backoff_sec)
        if source_wait_timeout_sec > 0:
            backoff_sec = min(
                backoff_sec,
                max(0.0, source_wait_timeout_sec - elapsed_sec),
            )
        if backoff_sec > 0:
            sleep(backoff_sec)
    return None


__all__ = ["acquire_initial_stream"]
