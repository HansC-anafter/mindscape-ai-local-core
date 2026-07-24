from __future__ import annotations

import pytest

from capabilities.motion_runtime.analysis.schema.live_motion_session import (
    LiveMotionSession,
)
from capabilities.motion_runtime.analysis.schema.motion_window_summary import MotionWindowSummary
from capabilities.motion_runtime.analysis.services.session_rollup_builder import (
    MotionSessionRollupBuilder,
)
from capabilities.motion_runtime.analysis.tools.mrt_analysis_append_motion_window import (
    mrt_analysis_append_motion_window,
)
from capabilities.motion_runtime.analysis.tools.mrt_analysis_register_live_session import (
    mrt_analysis_register_live_session,
)
from capabilities.motion_runtime.analysis.tools.runtime_registry import (
    reset_motion_analysis_runtime,
)


def _summary(
    window_id: str,
    start_ms: float,
    end_ms: float,
    *,
    findings: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    scores: dict[str, float] | None = None,
) -> MotionWindowSummary:
    return MotionWindowSummary(
        window_id=window_id,
        live_session_id="lms_segments",
        ts_start_ms=start_ms,
        ts_end_ms=end_ms,
        confidence_stats={"mean_confidence": 0.8, "mean_visible_ratio": 0.9},
        scores=scores or {"pose_confidence": 0.8},
        findings=findings or [],
        keypoint_frame_count=8,
        metadata=metadata or {},
    )


@pytest.mark.asyncio
async def test_register_live_session_accepts_known_producer_live_id() -> None:
    reset_motion_analysis_runtime()
    registered = await mrt_analysis_register_live_session(
        workspace_id="workspace-1",
        capture_session_id="capture-1",
        live_session_id="lms_known_producer",
    )

    assert registered["live_session"]["live_session_id"] == "lms_known_producer"


@pytest.mark.asyncio
async def test_append_motion_window_retry_is_idempotent_before_rate_limit() -> None:
    reset_motion_analysis_runtime()
    registered = await mrt_analysis_register_live_session(
        workspace_id="workspace-1",
        capture_session_id="capture-1",
    )
    live_session_id = registered["live_session"]["live_session_id"]
    payload = {
        "window_id": "window-retry-1",
        "live_session_id": live_session_id,
        "ts_start_ms": 0,
        "ts_end_ms": 500,
        "confidence_stats": {"mean_confidence": 0.8},
        "scores": {"pose_confidence": 0.8},
        "findings": [],
        "keypoint_frame_count": 8,
    }

    first = await mrt_analysis_append_motion_window(
        motion_window_summary=payload,
        received_at_ms=1000,
    )
    duplicate = await mrt_analysis_append_motion_window(
        motion_window_summary=payload,
        received_at_ms=1000,
    )

    assert first["accepted"] is True
    assert duplicate["accepted"] is True
    assert duplicate["idempotent"] is True
    assert duplicate["motion_window_ref"] == "window-retry-1"
    assert duplicate["summary_count"] == 1


def test_session_rollup_records_observed_reference_segments_without_validation() -> None:
    rollup = MotionSessionRollupBuilder().build(
        session=LiveMotionSession(
            live_session_id="lms_segments",
            workspace_id="workspace-1",
            capture_session_id="capture-1",
        ),
        summaries=[
            _summary("window-1", 0, 500),
            _summary("window-2", 20000, 20500),
        ],
    )

    metadata = rollup.metadata
    ledger = metadata["reference_segment_ledger"]
    assert ledger["validation_requested"] is False
    assert ledger["schema_version"] == "motion_reference_segment_ledger.v2"
    assert ledger["segmentation_mode"] == "adaptive_semantic"
    assert ledger["checkpoint_ms"] == 10000.0
    assert ledger["observed_segment_count"] == 2
    assert ledger["missing_segment_indexes"] == []
    assert ledger["observed_checkpoint_count"] == 2
    assert ledger["missing_checkpoint_indexes"] == [1]
    assert len(ledger["time_gaps"]) == 1
    assert "expected_validation_segment_count" not in ledger
    assert metadata["reference_segments"][0]["segment_id"] == "lms_segments:segment:001"
    assert metadata["reference_segments"][1]["segment_id"] == "lms_segments:segment:002"
    assert metadata["reference_segments"][1]["boundary_reason"] == "timeline_gap"
    assert rollup.motion_window_digests[0]["reference_segment"]["segment_id"] == (
        "lms_segments:segment:001"
    )


def test_session_rollup_validates_expected_duration_only_when_requested() -> None:
    rollup = MotionSessionRollupBuilder().build(
        session=LiveMotionSession(
            live_session_id="lms_segments",
            workspace_id="workspace-1",
            capture_session_id="capture-1",
        ),
        summaries=[
            _summary("window-1", 0, 500),
            _summary("window-2", 20000, 20500),
        ],
        metadata={"expected_duration_ms": 30000},
    )

    ledger = rollup.metadata["reference_segment_ledger"]
    assert ledger["validation_requested"] is True
    assert ledger["expected_validation_checkpoint_count"] == 3
    assert ledger["expected_validation_segment_count"] == 3
    assert ledger["missing_validation_checkpoint_indexes"] == [1]
    assert ledger["missing_validation_segment_indexes"] == [1]
    assert ledger["missing_checkpoint_indexes"] == [1]
    assert ledger["coverage_ratio"] == 0.667
    assert ledger["validation_ready"] is False
    assert ledger["validation_passed"] is False


def test_session_rollup_counts_cross_boundary_window_as_segment_coverage() -> None:
    rollup = MotionSessionRollupBuilder().build(
        session=LiveMotionSession(
            live_session_id="lms_segments",
            workspace_id="workspace-1",
            capture_session_id="capture-1",
        ),
        summaries=[
            _summary("window-1", 0, 500),
            _summary("window-cross", 9500, 10500),
        ],
        metadata={"expected_duration_ms": 20000},
    )

    ledger = rollup.metadata["reference_segment_ledger"]
    assert ledger["observed_segment_count"] == 2
    assert ledger["missing_segment_indexes"] == []
    assert ledger["observed_checkpoint_count"] == 2
    assert ledger["missing_checkpoint_indexes"] == []
    assert ledger["missing_validation_segment_indexes"] == []
    segments = rollup.metadata["reference_segments"]
    assert [segment["segment_index"] for segment in segments] == [0, 1]
    assert segments[1]["motion_window_refs"] == ["window-cross"]
    assert segments[1]["boundary_reason"] == "timeline_gap"
    assert len(ledger["time_gaps"]) == 1
    assert ledger["validation_ready"] is False
    assert ledger["validation_passed"] is False


def test_session_rollup_accepts_complete_checkpoints_with_tail_underflow() -> None:
    rollup = MotionSessionRollupBuilder().build(
        session=LiveMotionSession(
            live_session_id="lms_segments",
            workspace_id="workspace-1",
            capture_session_id="capture-1",
        ),
        summaries=[
            _summary("window-1", 0, 9500),
            _summary("window-2", 9500, 19950),
        ],
        metadata={"expected_duration_ms": 20000},
    )

    ledger = rollup.metadata["reference_segment_ledger"]
    assert rollup.duration_ms == 19950
    assert ledger["expected_validation_checkpoint_count"] == 2
    assert ledger["missing_validation_checkpoint_indexes"] == []
    assert ledger["coverage_ratio"] == 1.0
    assert ledger["time_gaps"] == []
    assert ledger["validation_ready"] is True
    assert ledger["validation_passed"] is True


def test_session_rollup_aggregates_semantic_segments_by_phase_shift() -> None:
    rollup = MotionSessionRollupBuilder().build(
        session=LiveMotionSession(
            live_session_id="lms_segments",
            workspace_id="workspace-1",
            capture_session_id="capture-1",
        ),
        summaries=[
            _summary(
                "window-hold",
                0,
                7600,
                metadata={"motion_phase": "warmup_hold"},
            ),
            _summary(
                "window-transition",
                8600,
                9000,
                metadata={"motion_phase": "downward_dog"},
            ),
        ],
    )

    ledger = rollup.metadata["reference_segment_ledger"]
    segments = rollup.metadata["reference_segments"]
    assert ledger["observed_segment_count"] == 2
    assert ledger["observed_checkpoint_count"] == 1
    assert [segment["boundary_reason"] for segment in segments] == [
        "session_start",
        "pack_phase_shift",
    ]


def test_session_rollup_keeps_fixed_interval_as_diagnostic_mode_only() -> None:
    rollup = MotionSessionRollupBuilder().build(
        session=LiveMotionSession(
            live_session_id="lms_segments",
            workspace_id="workspace-1",
            capture_session_id="capture-1",
        ),
        summaries=[
            _summary("window-1", 0, 500),
            _summary("window-2", 20000, 20500),
        ],
        metadata={"segmentation_mode": "fixed_interval"},
    )

    ledger = rollup.metadata["reference_segment_ledger"]
    assert ledger["segmentation_mode"] == "fixed_interval"
    assert ledger["observed_segment_count"] == 2
    assert ledger["missing_segment_indexes"] == [1]
    assert rollup.metadata["reference_segments"][1]["segment_id"] == (
        "lms_segments:segment:003"
    )
