from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .windows import MotionWindowAccumulator


@dataclass(frozen=True)
class TerminalMotionWindowResult:
    summary: dict[str, Any] | None
    event: dict[str, Any] | None


def finalize_terminal_motion_window(
    accumulator: MotionWindowAccumulator,
    terminal_end_ms: float,
) -> TerminalMotionWindowResult:
    pending_duration_ms = accumulator.pending_duration_ms(terminal_end_ms)
    if pending_duration_ms <= 0:
        return TerminalMotionWindowResult(summary=None, event=None)

    summary = accumulator.flush(terminal_end_ms)
    if summary is not None:
        return TerminalMotionWindowResult(
            summary=summary,
            event={
                "event": "terminal_motion_window_flushed",
                "window_id": summary["window_id"],
                "start_ms": summary["ts_start_ms"],
                "end_ms": summary["ts_end_ms"],
                "duration_ms": round(pending_duration_ms, 3),
            },
        )
    return TerminalMotionWindowResult(summary=None, event=None)


__all__ = ["TerminalMotionWindowResult", "finalize_terminal_motion_window"]
