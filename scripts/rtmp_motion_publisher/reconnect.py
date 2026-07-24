from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from .capture_metrics import CaptureMetricsLedger
from .session_policy import ReceiverSessionPolicy


ReconnectOutcome = Literal["reconnected", "session_complete", "failed", "stopped"]


@dataclass(frozen=True)
class ReconnectResult:
    outcome: ReconnectOutcome
    capture: Any | None
    first_frame: Any | None
    total_attempts: int


def reconnect_stream(
    *,
    args: Any,
    capture: Any,
    reason: str,
    started_at: float,
    total_attempts: int,
    policy: ReceiverSessionPolicy,
    capture_metrics: CaptureMetricsLedger,
    receiver_metrics: Callable[[int], dict[str, Any]],
    should_stop: Callable[[], bool],
    open_capture: Callable[[Any], Any],
    emit_event: Callable[[dict[str, Any]], None],
    transition_state: Callable[..., None],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> ReconnectResult:
    capture_metrics.close_generation(capture)
    capture.release()
    outage_attempts = 0
    while not should_stop():
        now = monotonic()
        block_reason = policy.reconnect_block_reason(
            now_monotonic=now,
            outage_attempts=outage_attempts,
        )
        if block_reason is not None:
            emit_event(
                {
                    "event": "stream_reconnect_give_up",
                    "reason": block_reason,
                    "trigger": reason,
                    "attempts": total_attempts,
                    "outage_attempts": outage_attempts,
                    "elapsed_sec": round(now - started_at, 3),
                }
            )
            outcome: ReconnectOutcome = (
                "session_complete"
                if block_reason == "session_deadline_reached"
                else "failed"
            )
            return ReconnectResult(outcome, None, None, total_attempts)

        total_attempts += 1
        outage_attempts += 1
        emit_event(
            {
                "event": "stream_reconnect_started",
                "reason": reason,
                "attempt": total_attempts,
                "outage_attempt": outage_attempts,
                "elapsed_sec": round(now - started_at, 3),
            }
        )
        transition_state(
            args,
            "degraded",
            reason=reason,
            metrics=receiver_metrics(total_attempts),
        )
        delay = policy.bounded_delay(
            args.stream_reconnect_backoff_sec,
            now_monotonic=now,
        )
        if delay > 0:
            sleep(delay)
        if policy.is_complete(monotonic()):
            continue

        replacement = open_capture(args)
        if replacement.isOpened():
            first_frame_ok, first_frame = replacement.read()
            if first_frame_ok:
                emit_event(
                    {
                        "event": "stream_reconnected",
                        "attempt": total_attempts,
                        "outage_attempt": outage_attempts,
                        "elapsed_sec": round(monotonic() - started_at, 3),
                    }
                )
                transition_state(
                    args,
                    "analyzing",
                    metrics=receiver_metrics(total_attempts),
                )
                return ReconnectResult(
                    "reconnected",
                    replacement,
                    first_frame,
                    total_attempts,
                )
            failure_reason = "initial_frame_unavailable"
        else:
            failure_reason = "stream_not_open"
        capture_metrics.close_generation(replacement)
        replacement.release()
        emit_event(
            {
                "event": "stream_reconnect_failed",
                "reason": failure_reason,
                "attempt": total_attempts,
                "outage_attempt": outage_attempts,
                "elapsed_sec": round(monotonic() - started_at, 3),
            }
        )
    return ReconnectResult("stopped", None, None, total_attempts)


__all__ = ["ReconnectResult", "reconnect_stream"]
