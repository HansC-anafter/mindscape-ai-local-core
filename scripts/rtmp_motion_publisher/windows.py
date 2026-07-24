from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


POSTURE_METRIC_KEYS = (
    "left_elbow_flexion",
    "right_elbow_flexion",
    "left_shoulder_flexion",
    "right_shoulder_flexion",
    "left_hip_flexion",
    "right_hip_flexion",
    "left_knee_flexion",
    "right_knee_flexion",
    "torso_horizontal",
    "wrist_ankle_vertical_gap",
    "body_aspect",
)


@dataclass
class PoseSample:
    timestamp_ms: float
    confidence: float
    visible_point_count: int
    total_point_count: int
    findings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class PendingMotionWindow:
    summary: dict[str, Any]
    received_at_ms: float
    append_confirmation_rounds: int = 0
    append_first_failure_monotonic: float | None = None
    append_next_confirmation_monotonic: float = 0.0


@dataclass
class MotionWindowAccumulator:
    live_session_id: str
    source_session_id: str
    window_ms: float
    max_samples: int
    sequence: int = 0
    window_start_ms: float | None = None
    samples: list[PoseSample] = field(default_factory=list)

    def push(self, sample: PoseSample) -> dict[str, Any] | None:
        if self.window_start_ms is None:
            self.window_start_ms = sample.timestamp_ms
        if len(self.samples) < self.max_samples:
            self.samples.append(sample)
        if sample.timestamp_ms - self.window_start_ms < self.window_ms:
            return None
        summary = self.flush(sample.timestamp_ms)
        if summary is not None:
            self.window_start_ms = sample.timestamp_ms
            self.samples = [sample]
        return summary

    def pending_duration_ms(self, end_ms: float | None = None) -> float:
        if self.window_start_ms is None or not self.samples:
            return 0.0
        resolved_end_ms = float(
            end_ms if end_ms is not None else self.samples[-1].timestamp_ms
        )
        return max(0.0, resolved_end_ms - self.window_start_ms)

    def flush(
        self,
        end_ms: float | None = None,
        *,
        minimum_duration_ms: float = 0.0,
    ) -> dict[str, Any] | None:
        if self.window_start_ms is None or not self.samples:
            return None
        if self.pending_duration_ms(end_ms) < max(0.0, minimum_duration_ms):
            return None
        confidence_values = [sample.confidence for sample in self.samples]
        visible_ratios = [
            sample.visible_point_count / sample.total_point_count
            if sample.total_point_count > 0
            else 0.0
            for sample in self.samples
        ]
        mean_confidence = round(sum(confidence_values) / len(confidence_values), 3)
        mean_visible_ratio = round(sum(visible_ratios) / len(visible_ratios), 3)
        findings = sorted(
            {
                finding
                for sample in self.samples
                for finding in sample.findings
                if str(finding).strip()
            }
        )
        compact_metrics = self._compact_metrics()
        if mean_confidence < 0.4 or mean_visible_ratio < 0.4:
            findings.append("pose_visibility_low")
        if compact_metrics.get("center_x_range", 0.0) >= 0.14:
            findings.append("center_lateral_sway")
        if compact_metrics.get("center_y_range", 0.0) >= 0.14:
            findings.append("center_vertical_sway")
        if abs(compact_metrics.get("shoulder_line_tilt_mean", 0.0)) >= 0.08:
            findings.append("shoulder_line_tilt")
        if abs(compact_metrics.get("hip_line_tilt_mean", 0.0)) >= 0.08:
            findings.append("hip_stack_variation")
        findings = sorted(dict.fromkeys(findings))
        domain_metrics = self._domain_metrics(
            compact_metrics=compact_metrics,
            confidence=mean_confidence,
            visible_ratio=mean_visible_ratio,
        )
        window_id = (
            f"{self.live_session_id}:motion-window:"
            f"{round(self.window_start_ms)}:{self.sequence}"
        )
        self.sequence += 1
        summary = {
            "window_id": window_id,
            "live_session_id": self.live_session_id,
            "ts_start_ms": round(self.window_start_ms, 3),
            "ts_end_ms": round(
                float(end_ms if end_ms is not None else self.samples[-1].timestamp_ms),
                3,
            ),
            "skeleton_family": "mediapipe_pose_33",
            "confidence_stats": {
                "mean_confidence": mean_confidence,
                "mean_visible_ratio": mean_visible_ratio,
                "sample_count": len(self.samples),
            },
            "scores": {
                "pose_confidence": mean_confidence,
                "body_visibility": mean_visible_ratio,
            },
            "findings": findings,
            "keypoint_frame_count": len(self.samples),
            "metadata": {
                "source": "live_motion_receiver",
                "source_session_id": self.source_session_id,
                "pose_provider": "mediapipe_pose",
                "provider_code": "host_python_mediapipe_pose_solution",
                "provider_schema_id": "mediapipe_pose_solution_video",
                "keypoint_schema_id": "mediapipe_pose_33",
                "motion_metric_schema_version": "live_motion_window.v1",
                "window_ms": self.window_ms,
                "max_samples": self.max_samples,
                "compact_motion_metrics": compact_metrics,
                **domain_metrics,
            },
        }
        self.reset()
        return summary

    def _metric_values(self, key: str) -> list[float]:
        values: list[float] = []
        for sample in self.samples:
            value = sample.metrics.get(key)
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    def _metric_mean(self, key: str) -> float:
        values = self._metric_values(key)
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    def _metric_range(self, key: str) -> float:
        values = self._metric_values(key)
        if not values:
            return 0.0
        return round(max(values) - min(values), 4)

    def _compact_metrics(self) -> dict[str, float]:
        metrics = {
            "center_x_mean": self._metric_mean("center_x"),
            "center_y_mean": self._metric_mean("center_y"),
            "center_x_range": self._metric_range("center_x"),
            "center_y_range": self._metric_range("center_y"),
            "shoulder_line_tilt_mean": self._metric_mean("shoulder_line_tilt"),
            "hip_line_tilt_mean": self._metric_mean("hip_line_tilt"),
            "torso_length_mean": self._metric_mean("torso_length"),
            "body_width_mean": self._metric_mean("body_width"),
        }
        metrics.update(
            {
                f"{key}_mean": self._metric_mean(key)
                for key in POSTURE_METRIC_KEYS
                if self._metric_values(key)
            }
        )
        return metrics

    def _domain_metrics(
        self,
        *,
        compact_metrics: dict[str, float],
        confidence: float,
        visible_ratio: float,
    ) -> dict[str, Any]:
        shoulder_tilt = abs(compact_metrics.get("shoulder_line_tilt_mean", 0.0))
        hip_tilt = abs(compact_metrics.get("hip_line_tilt_mean", 0.0))
        center_x_range = compact_metrics.get("center_x_range", 0.0)
        center_y_range = compact_metrics.get("center_y_range", 0.0)
        stability_delta = round(max(0.0, 1.0 - min(confidence, visible_ratio)), 4)
        return {
            "dwpose_node_deltas": [
                {
                    "node_id": "shoulder_line",
                    "delta_score": round(shoulder_tilt, 4),
                    "confidence": confidence,
                    "metric_source": "mediapipe_compact_pose_summary",
                    "finding": "Shoulder line is tilted." if shoulder_tilt >= 0.08 else "Shoulder line stayed readable.",
                    "guidance": "Keep both collarbones broad and level.",
                },
                {
                    "node_id": "hip_stack",
                    "delta_score": round(hip_tilt, 4),
                    "confidence": confidence,
                    "metric_source": "mediapipe_compact_pose_summary",
                    "finding": "Hip line shifted." if hip_tilt >= 0.08 else "Hip line stayed readable.",
                    "guidance": "Keep the pelvis even before increasing range.",
                },
            ],
            "sway_metrics": [
                {
                    "axis": "center_stability",
                    "delta_score": round(max(center_x_range, center_y_range), 4),
                    "confidence": confidence,
                    "metric_source": "mediapipe_compact_pose_summary",
                    "finding": "Center line shifted." if max(center_x_range, center_y_range) >= 0.14 else "Center line remained steady.",
                    "guidance": "Keep the breath slow and let the center line settle.",
                }
            ],
            "phase_metrics": [
                {
                    "phase": "hold_stability",
                    "delta_score": stability_delta,
                    "confidence": confidence,
                    "metric_source": "mediapipe_compact_pose_summary",
                    "finding": "Pose visibility or hold stability dropped." if stability_delta >= 0.35 else "Hold stability stayed high.",
                    "guidance": "Maintain the same calm pace and alignment.",
                }
            ],
        }

    def reset(self) -> None:
        self.window_start_ms = None
        self.samples = []
