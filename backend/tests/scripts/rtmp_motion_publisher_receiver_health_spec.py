from __future__ import annotations

from scripts.rtmp_motion_publisher.receiver_health import receiver_metrics


def test_receiver_metrics_projects_bounded_pipe_counters() -> None:
    metrics = receiver_metrics(
        attempted_windows=8,
        sender_stats={
            "accepted_windows": 7,
            "rejected_windows": 1,
            "failed_windows": 0,
            "append_queue_pending": 0,
        },
        capture_stats={
            "decoded_frames": 140,
            "overwritten_frames": 80,
            "decode_errors": 1,
            "pipe_bytes_read": 3_700_000,
            "pipe_buffered_bytes": 128,
            "pipe_high_watermark_bytes": 28_000,
            "pipe_discarded_bytes": 12,
            "pipe_overflow_count": 0,
            "raw_frame": "forbidden",
        },
        reconnect_attempts=2,
        last_window_summary={
            "ts_end_ms": 32_000.0,
            "metadata": {
                "reference_alignment": {
                    "chapter_id": "segment:010",
                    "localization_ready": True,
                }
            },
        },
    )

    assert metrics == {
        "attempted_windows": 8,
        "accepted_windows": 7,
        "rejected_windows": 1,
        "failed_windows": 0,
        "append_queue_pending": 0,
        "reconnect_attempts": 2,
        "decoded_frames": 140,
        "overwritten_frames": 80,
        "decode_errors": 1,
        "pipe_bytes_read": 3_700_000,
        "pipe_buffered_bytes": 128,
        "pipe_high_watermark_bytes": 28_000,
        "pipe_discarded_bytes": 12,
        "pipe_overflow_count": 0,
        "last_window_end_ms": 32_000.0,
        "reference_chapter_id": "segment:010",
        "reference_localization_ready": True,
    }
