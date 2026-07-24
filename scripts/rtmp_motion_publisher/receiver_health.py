"""Bounded receiver health projection helpers."""

from __future__ import annotations

from typing import Any


def public_reference_alignment_status(
    summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    metadata = summary.get("metadata")
    if not isinstance(metadata, dict):
        return None
    alignment = metadata.get("reference_alignment")
    if not isinstance(alignment, dict):
        return None
    allowed_keys = (
        "chapter_id",
        "reference_window_index",
        "score",
        "localization_score",
        "confidence",
        "verdict",
        "localization_ready",
        "selection_mode",
        "sequence_history_size",
        "global_candidate_chapter_id",
        "global_candidate_score",
        "full_sequence_candidate_chapter_id",
        "full_sequence_candidate_score",
        "local_candidate_chapter_id",
        "local_candidate_score",
        "previous_chapter_candidate_chapter_id",
        "previous_chapter_candidate_score",
        "ordered_transition_supported",
        "pending_transition_chapter_id",
        "pending_transition_count",
        "pending_relock_chapter_id",
        "pending_relock_count",
    )
    return {key: alignment[key] for key in allowed_keys if key in alignment}


def receiver_metrics(
    *,
    attempted_windows: int,
    sender_stats: dict[str, Any],
    capture_stats: dict[str, Any] | None,
    source_wait_attempts: int,
    reconnect_attempts: int,
    last_window_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    alignment = public_reference_alignment_status(last_window_summary)
    capture = capture_stats or {}
    return {
        "attempted_windows": attempted_windows,
        "accepted_windows": sender_stats.get("accepted_windows", 0),
        "rejected_windows": sender_stats.get("rejected_windows", 0),
        "failed_windows": sender_stats.get("failed_windows", 0),
        "append_queue_pending": sender_stats.get("append_queue_pending", 0),
        "source_wait_attempts": source_wait_attempts,
        "reconnect_attempts": reconnect_attempts,
        "decoded_frames": capture.get("decoded_frames", 0),
        "overwritten_frames": capture.get("overwritten_frames", 0),
        "decode_errors": capture.get("decode_errors", 0),
        "pipe_bytes_read": capture.get("pipe_bytes_read", 0),
        "pipe_buffered_bytes": capture.get("pipe_buffered_bytes", 0),
        "pipe_high_watermark_bytes": capture.get("pipe_high_watermark_bytes", 0),
        "pipe_discarded_bytes": capture.get("pipe_discarded_bytes", 0),
        "pipe_overflow_count": capture.get("pipe_overflow_count", 0),
        "pipe_idle_timeout_count": capture.get("pipe_idle_timeout_count", 0),
        "last_window_end_ms": (
            last_window_summary.get("ts_end_ms")
            if last_window_summary is not None
            else None
        ),
        "reference_chapter_id": (
            alignment.get("chapter_id") if alignment is not None else None
        ),
        "reference_localization_ready": (
            alignment.get("localization_ready") if alignment is not None else None
        ),
    }


def publisher_status_event(
    *,
    elapsed_sec: float,
    attempted_windows: int,
    sender_stats: dict[str, Any],
    capture_stats: dict[str, Any],
    analysis_stats: dict[str, object],
    last_window_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "event": "publisher_status",
        "elapsed_sec": round(elapsed_sec, 3),
        "attempted_windows": attempted_windows,
        **sender_stats,
        "capture": capture_stats,
        "analysis": analysis_stats,
        "last_confidence": (
            last_window_summary["confidence_stats"]["mean_confidence"]
            if last_window_summary is not None
            else None
        ),
        "last_findings": (
            last_window_summary["findings"]
            if last_window_summary is not None
            else []
        ),
        "reference_alignment": public_reference_alignment_status(
            last_window_summary
        ),
    }


__all__ = [
    "public_reference_alignment_status",
    "publisher_status_event",
    "receiver_metrics",
]
