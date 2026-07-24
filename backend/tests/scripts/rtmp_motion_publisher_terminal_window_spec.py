from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.terminal_window import (  # noqa: E402
    finalize_terminal_motion_window,
)
from rtmp_motion_publisher.windows import (  # noqa: E402
    MotionWindowAccumulator,
    PoseSample,
)


def _accumulator_with_sample() -> MotionWindowAccumulator:
    accumulator = MotionWindowAccumulator(
        live_session_id="live-one",
        source_session_id="source-one",
        window_ms=2_000.0,
        max_samples=10,
    )
    assert accumulator.push(
        PoseSample(
            timestamp_ms=1_000.0,
            confidence=0.9,
            visible_point_count=30,
            total_point_count=33,
        )
    ) is None
    return accumulator


def test_terminal_window_below_ingest_interval_is_flushed_without_losing_coverage() -> None:
    result = finalize_terminal_motion_window(
        _accumulator_with_sample(),
        1_300.0,
    )

    assert result.summary is not None
    assert result.summary["ts_start_ms"] == 1_000.0
    assert result.summary["ts_end_ms"] == 1_300.0
    assert result.event == {
        "event": "terminal_motion_window_flushed",
        "window_id": result.summary["window_id"],
        "start_ms": 1_000.0,
        "end_ms": 1_300.0,
        "duration_ms": 300.0,
    }


def test_terminal_window_at_ingest_interval_is_flushed() -> None:
    result = finalize_terminal_motion_window(
        _accumulator_with_sample(),
        1_500.0,
    )

    assert result.summary is not None
    assert result.summary["ts_start_ms"] == 1_000.0
    assert result.summary["ts_end_ms"] == 1_500.0
    assert result.event == {
        "event": "terminal_motion_window_flushed",
        "window_id": result.summary["window_id"],
        "start_ms": 1_000.0,
        "end_ms": 1_500.0,
        "duration_ms": 500.0,
    }


def test_terminal_window_without_samples_has_no_event() -> None:
    accumulator = MotionWindowAccumulator(
        live_session_id="live-one",
        source_session_id="source-one",
        window_ms=2_000.0,
        max_samples=10,
    )

    result = finalize_terminal_motion_window(accumulator, 1_500.0)

    assert result.summary is None
    assert result.event is None


def test_completed_windows_share_the_real_boundary_sample() -> None:
    accumulator = MotionWindowAccumulator(
        live_session_id="live-one",
        source_session_id="source-one",
        window_ms=2_000.0,
        max_samples=10,
    )

    assert accumulator.push(
        PoseSample(
            timestamp_ms=0.0,
            confidence=0.9,
            visible_point_count=30,
            total_point_count=33,
        )
    ) is None
    first = accumulator.push(
        PoseSample(
            timestamp_ms=2_000.0,
            confidence=0.9,
            visible_point_count=30,
            total_point_count=33,
        )
    )
    second = accumulator.push(
        PoseSample(
            timestamp_ms=9_000.0,
            confidence=0.9,
            visible_point_count=30,
            total_point_count=33,
        )
    )

    assert first is not None
    assert second is not None
    assert first["ts_end_ms"] == second["ts_start_ms"] == 2_000.0
    assert second["ts_end_ms"] == 9_000.0
