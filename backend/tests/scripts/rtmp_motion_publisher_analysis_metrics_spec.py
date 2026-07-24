from __future__ import annotations

from scripts.rtmp_motion_publisher.analysis_metrics import AnalysisStageMetrics


def test_analysis_stage_metrics_report_bounded_stage_and_schedule_diagnostics() -> None:
    samples = iter([1.0, 1.025, 2.0, 2.075])
    metrics = AnalysisStageMetrics(clock=lambda: next(samples))

    first = metrics.started()
    metrics.record("pose", first)
    second = metrics.started()
    metrics.record("pose", second)
    metrics.record_sample_schedule_lag(sampled_at=4.3, scheduled_at=4.0)

    assert metrics.snapshot() == {
        "stages": {
            "pose": {
                "count": 2,
                "total_ms": 100.0,
                "mean_ms": 50.0,
                "max_ms": 75.0,
            }
        },
        "sample_schedule_lag": {
            "count": 1,
            "total_ms": 300.0,
            "mean_ms": 300.0,
            "max_ms": 300.0,
        },
    }
