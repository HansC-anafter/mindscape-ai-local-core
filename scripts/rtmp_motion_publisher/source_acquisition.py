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
    source_wait_attempts = 0
    input_uri = public_input_uri(args.rtmp_url)
    while not should_stop():
        capture = open_capture(args)
        reason = "stream_not_open"
        if capture.isOpened():
            first_frame_ok, first_frame = capture.read()
            if first_frame_ok:
                return capture, first_frame, source_wait_attempts
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
        wait_expired = (
            source_wait_timeout_sec > 0
            and elapsed_sec >= source_wait_timeout_sec
        )
        attempts_exhausted = (
            int(getattr(args, "source_wait_max_attempts", 0) or 0) > 0
            and source_wait_attempts
            >= int(getattr(args, "source_wait_max_attempts", 0) or 0)
        )
        if wait_expired or attempts_exhausted:
            emit_event(
                {
                    "event": "source_wait_expired",
                    "reason": (
                        "source_wait_budget_exhausted"
                        if attempts_exhausted
                        else reason
                    ),
                    "trigger": reason,
                    "attempts": source_wait_attempts,
                    "elapsed_sec": round(elapsed_sec, 3),
                }
            )
            return None

        source_wait_attempts += 1
        emit_event(
            {
                "event": "source_wait_retry_started",
                "reason": reason,
                "attempt": source_wait_attempts,
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
