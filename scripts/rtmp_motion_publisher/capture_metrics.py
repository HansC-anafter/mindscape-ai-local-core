from __future__ import annotations

from typing import Any


_SUM_COUNTERS = (
    "decoded_frames",
    "overwritten_frames",
    "decode_errors",
    "pipe_bytes_read",
    "pipe_discarded_bytes",
    "pipe_overflow_count",
    "pipe_idle_timeout_count",
)


def _capture_stats(capture: Any) -> dict[str, Any]:
    stats = getattr(capture, "stats", None)
    return dict(stats()) if callable(stats) else {}


class CaptureMetricsLedger:
    """Preserve bounded capture counters across reconnect generations."""

    def __init__(self) -> None:
        self._totals = {key: 0 for key in _SUM_COUNTERS}
        self._pipe_high_watermark_bytes = 0
        self._last_reader_error: str | None = None

    def snapshot(self, capture: Any) -> dict[str, Any]:
        current = (
            {}
            if bool(getattr(capture, "_capture_metrics_archived", False))
            else _capture_stats(capture)
        )
        snapshot = {
            key: self._totals[key] + max(0, int(current.get(key) or 0))
            for key in _SUM_COUNTERS
        }
        snapshot["pipe_buffered_bytes"] = max(
            0,
            int(current.get("pipe_buffered_bytes") or 0),
        )
        snapshot["pipe_high_watermark_bytes"] = max(
            self._pipe_high_watermark_bytes,
            max(0, int(current.get("pipe_high_watermark_bytes") or 0)),
        )
        snapshot["reader_error"] = (
            str(current.get("reader_error") or "").strip() or None
            if "reader_error" in current
            else self._last_reader_error
        )
        return snapshot

    def close_generation(self, capture: Any) -> None:
        if bool(getattr(capture, "_capture_metrics_archived", False)):
            return
        current = _capture_stats(capture)
        for key in _SUM_COUNTERS:
            self._totals[key] += max(0, int(current.get(key) or 0))
        self._pipe_high_watermark_bytes = max(
            self._pipe_high_watermark_bytes,
            max(0, int(current.get("pipe_high_watermark_bytes") or 0)),
        )
        reader_error = str(current.get("reader_error") or "").strip()
        if reader_error:
            self._last_reader_error = reader_error
        setattr(capture, "_capture_metrics_archived", True)


__all__ = ["CaptureMetricsLedger"]
