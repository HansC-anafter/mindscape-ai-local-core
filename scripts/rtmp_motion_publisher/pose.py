from __future__ import annotations

import math
from typing import Any

import mediapipe as mp

from .windows import PoseSample


class PoseDetector:
    def __init__(self, detector: Any, running_mode: str) -> None:
        self.detector = detector
        self.running_mode = running_mode

    @classmethod
    def create(cls, model_asset_path: str) -> "PoseDetector":
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
            return cls(
                mp.solutions.pose.Pose(
                    static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                ),
                "solutions",
            )
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_asset_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
        return cls(vision.PoseLandmarker.create_from_options(options), "tasks")

    def process(self, rgb_frame: Any, timestamp_ms: float) -> Any:
        if self.running_mode == "solutions":
            return self.detector.process(rgb_frame)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        return self.detector.detect_for_video(mp_image, int(timestamp_ms))

    def close(self) -> None:
        self.detector.close()


def _landmark_list(result: Any) -> list[Any]:
    pose_landmarks = getattr(result, "pose_landmarks", None)
    if pose_landmarks is None:
        return []
    if isinstance(pose_landmarks, list):
        return list(pose_landmarks[0]) if pose_landmarks else []
    landmarks = getattr(pose_landmarks, "landmark", None)
    return list(landmarks or [])


def _visibility(landmark: Any) -> float:
    return max(0.0, min(1.0, float(getattr(landmark, "visibility", 0.0) or 0.0)))


def _point(landmarks: list[Any], index: int) -> tuple[float, float] | None:
    if index >= len(landmarks):
        return None
    landmark = landmarks[index]
    if _visibility(landmark) < 0.35:
        return None
    return (
        max(0.0, min(1.0, float(getattr(landmark, "x", 0.0) or 0.0))),
        max(0.0, min(1.0, float(getattr(landmark, "y", 0.0) or 0.0))),
    )


def _midpoint(
    first: tuple[float, float] | None,
    second: tuple[float, float] | None,
) -> tuple[float, float] | None:
    if first is None or second is None:
        return None
    return ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)


def _distance(
    first: tuple[float, float] | None,
    second: tuple[float, float] | None,
) -> float:
    if first is None or second is None:
        return 0.0
    return math.dist(first, second)


def _joint_angle(
    first: tuple[float, float] | None,
    vertex: tuple[float, float] | None,
    third: tuple[float, float] | None,
) -> float | None:
    if first is None or vertex is None or third is None:
        return None
    first_vector = (first[0] - vertex[0], first[1] - vertex[1])
    third_vector = (third[0] - vertex[0], third[1] - vertex[1])
    denominator = math.hypot(*first_vector) * math.hypot(*third_vector)
    if denominator <= 1e-8:
        return None
    cosine = max(
        -1.0,
        min(
            1.0,
            (first_vector[0] * third_vector[0] + first_vector[1] * third_vector[1])
            / denominator,
        ),
    )
    return round(math.acos(cosine) / math.pi, 4)


def _add_joint_angle(
    metrics: dict[str, float],
    key: str,
    first: tuple[float, float] | None,
    vertex: tuple[float, float] | None,
    third: tuple[float, float] | None,
) -> None:
    value = _joint_angle(first, vertex, third)
    if value is not None:
        metrics[key] = value


def _compact_pose_metrics(landmarks: list[Any]) -> dict[str, float]:
    visible_points = [
        _point(landmarks, index)
        for index in range(len(landmarks))
    ]
    visible_points = [point for point in visible_points if point is not None]
    left_shoulder = _point(landmarks, 11)
    right_shoulder = _point(landmarks, 12)
    left_hip = _point(landmarks, 23)
    right_hip = _point(landmarks, 24)
    left_elbow = _point(landmarks, 13)
    right_elbow = _point(landmarks, 14)
    left_wrist = _point(landmarks, 15)
    right_wrist = _point(landmarks, 16)
    left_knee = _point(landmarks, 25)
    right_knee = _point(landmarks, 26)
    left_ankle = _point(landmarks, 27)
    right_ankle = _point(landmarks, 28)
    shoulder_mid = _midpoint(left_shoulder, right_shoulder)
    hip_mid = _midpoint(left_hip, right_hip)
    if visible_points:
        center_x = sum(point[0] for point in visible_points) / len(visible_points)
        center_y = sum(point[1] for point in visible_points) / len(visible_points)
    else:
        center_x = 0.0
        center_y = 0.0
    metrics = {
        "center_x": round(center_x, 4),
        "center_y": round(center_y, 4),
        "shoulder_line_tilt": round(
            (left_shoulder[1] - right_shoulder[1])
            if left_shoulder is not None and right_shoulder is not None
            else 0.0,
            4,
        ),
        "hip_line_tilt": round(
            (left_hip[1] - right_hip[1])
            if left_hip is not None and right_hip is not None
            else 0.0,
            4,
        ),
        "torso_length": round(_distance(shoulder_mid, hip_mid), 4),
        "body_width": round(_distance(left_shoulder, right_shoulder), 4),
    }
    _add_joint_angle(metrics, "left_elbow_flexion", left_shoulder, left_elbow, left_wrist)
    _add_joint_angle(metrics, "right_elbow_flexion", right_shoulder, right_elbow, right_wrist)
    _add_joint_angle(metrics, "left_shoulder_flexion", left_elbow, left_shoulder, left_hip)
    _add_joint_angle(metrics, "right_shoulder_flexion", right_elbow, right_shoulder, right_hip)
    _add_joint_angle(metrics, "left_hip_flexion", left_shoulder, left_hip, left_knee)
    _add_joint_angle(metrics, "right_hip_flexion", right_shoulder, right_hip, right_knee)
    _add_joint_angle(metrics, "left_knee_flexion", left_hip, left_knee, left_ankle)
    _add_joint_angle(metrics, "right_knee_flexion", right_hip, right_knee, right_ankle)
    torso_length = _distance(shoulder_mid, hip_mid)
    if shoulder_mid is not None and hip_mid is not None and torso_length > 1e-8:
        metrics["torso_horizontal"] = round(
            abs(shoulder_mid[0] - hip_mid[0]) / torso_length,
            4,
        )
    wrist_mid = _midpoint(left_wrist, right_wrist)
    ankle_mid = _midpoint(left_ankle, right_ankle)
    if wrist_mid is not None and ankle_mid is not None:
        metrics["wrist_ankle_vertical_gap"] = round(
            abs(wrist_mid[1] - ankle_mid[1]),
            4,
        )
    if visible_points:
        width = max(point[0] for point in visible_points) - min(
            point[0] for point in visible_points
        )
        height = max(point[1] for point in visible_points) - min(
            point[1] for point in visible_points
        )
        if width + height > 1e-8:
            metrics["body_aspect"] = round(width / (width + height), 4)
    return metrics


def pose_sample_from_result(result: Any, timestamp_ms: float) -> PoseSample:
    landmarks = _landmark_list(result)
    if not landmarks:
        return PoseSample(
            timestamp_ms=timestamp_ms,
            confidence=0.0,
            visible_point_count=0,
            total_point_count=33,
        )
    visibility_values = [
        _visibility(landmark)
        for landmark in landmarks
    ]
    if not visibility_values:
        return PoseSample(
            timestamp_ms=timestamp_ms,
            confidence=0.0,
            visible_point_count=0,
            total_point_count=33,
        )
    return PoseSample(
        timestamp_ms=timestamp_ms,
        confidence=round(sum(visibility_values) / len(visibility_values), 3),
        visible_point_count=sum(1 for value in visibility_values if value >= 0.5),
        total_point_count=len(visibility_values),
        metrics=_compact_pose_metrics(landmarks),
    )
