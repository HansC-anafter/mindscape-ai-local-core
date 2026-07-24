from __future__ import annotations

import json
from typing import Any

from capabilities.motion_runtime.analysis.schema.motion_session_rollup import (
    MotionSessionRollup,
)
from capabilities.motion_runtime.analysis.services.analysis_artifact_registry_publisher import (
    AnalysisArtifactRegistryPublisher,
)


class _Artifact:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _ArtifactType:
    DATA = "data"


class _PrimaryActionType:
    PREVIEW = "preview"


class _ArtifactStore:
    def __init__(self) -> None:
        self.created: list[_Artifact] = []

    def create_artifact(self, artifact: _Artifact) -> None:
        payload_size = len(json.dumps(artifact.content).encode("utf-8"))
        if payload_size > 16_384:
            raise ValueError(
                f"artifact content exceeds 16384 byte budget ({payload_size} bytes)"
            )
        self.created.append(artifact)


def _large_digest(index: int) -> dict[str, Any]:
    return {
        "motion_window_ref": f"lms_demo:window:{index}",
        "window_index": index,
        "start_ms": index * 2000,
        "end_ms": index * 2000 + 1800,
        "confidence": 0.72,
        "source_session_id": "device_session_phone",
        "pose_provider": "mediapipe_pose",
        "provider_code": "browser_mediapipe_pose_lite",
        "keypoint_schema_id": "mediapipe_pose_33",
        "top_findings": [
            "Keep the body centered over the base while holding this practice window.",
            "Slow the next breath cycle before transitioning.",
        ],
        "dwpose_node_deltas": [
            {
                "node_id": f"node_{nested}",
                "node_label": f"Node {nested}",
                "delta_score": 0.1 + nested / 100,
                "finding": "Long alignment finding that would inflate the rollup artifact.",
                "guidance": "Long alignment guidance that should be bounded in artifact preview.",
            }
            for nested in range(8)
        ],
        "sway_metrics": [
            {
                "axis": "front_back",
                "delta_score": 0.2 + nested / 100,
                "finding": "Long sway finding that would inflate repeated window records.",
                "guidance": "Long sway guidance that should be bounded in artifact preview.",
            }
            for nested in range(6)
        ],
        "phase_metrics": [
            {
                "phase": "hold",
                "delta_score": 0.3 + nested / 100,
                "finding": "Long phase finding that would inflate repeated window records.",
                "guidance": "Long phase guidance that should be bounded in artifact preview.",
            }
            for nested in range(6)
        ],
    }


def test_motion_rollup_artifact_publisher_keeps_content_within_registry_budget(
    monkeypatch,
) -> None:
    store = _ArtifactStore()
    publisher = AnalysisArtifactRegistryPublisher()
    monkeypatch.setattr(
        publisher,
        "_load_backend_components",
        lambda: {
            "Artifact": _Artifact,
            "ArtifactType": _ArtifactType,
            "PrimaryActionType": _PrimaryActionType,
            "artifacts_store": store,
        },
    )
    rollup = MotionSessionRollup(
        rollup_id="lms_demo:rollup:80",
        motion_rollup_ref="mindscape://motion_runtime/analysis/session-rollup/lms_demo",
        live_session_id="lms_demo",
        workspace_id="ws_demo",
        capture_session_id="device_session_phone",
        device_profile_ref="mindscape://device_binding/session/device_session_phone",
        meeting_session_id="meeting_demo",
        expert_library_ref=None,
        source_refs=[{"ref_type": "capture_session", "capture_session_id": "device_session_phone"}],
        instruction_refs=[{"ref_type": "manual_ref", "video_ref": "mindscape://lesson/demo"}],
        window_count=80,
        duration_ms=160000.0,
        confidence_stats={"mean_confidence": 0.72, "window_count": 80.0},
        score_summary={"pose_confidence": 0.72},
        finding_counts={"alignment": 12},
        top_findings=["Level both shoulders before holding the pose."],
        motion_window_refs=[f"lms_demo:window:{index}" for index in range(80)],
        motion_window_digests=[_large_digest(index) for index in range(80)],
        created_at="2026-06-15T00:00:00+00:00",
        metadata={
            "schema_version": "motion_session_rollup.v1",
            "source": "motion_runtime.analysis",
            "window_ref_cap": 100,
            "window_refs_truncated": False,
            "course_chapters": [{"chapter_id": f"chapter_{index}"} for index in range(20)],
        },
    )

    result = publisher.publish(workspace_id="ws_demo", rollup=rollup)

    assert result["status"] == "created"
    assert result["rollup_artifact_id"]
    assert len(store.created) == 1
    content = store.created[0].content
    assert len(json.dumps(content).encode("utf-8")) < 16_384
    artifact_rollup = content["motion_session_rollup"]
    assert artifact_rollup["window_count"] == 80
    assert artifact_rollup["motion_window_ref_count"] == 80
    assert artifact_rollup["motion_window_refs_sample"] == rollup.motion_window_refs[:5]
    assert artifact_rollup["motion_window_refs_tail_sample"] == rollup.motion_window_refs[-5:]
    assert artifact_rollup["motion_window_ref_policy"] == {
        "artifact_sample_cap": 5,
        "original_ref_count": 80,
        "truncated": True,
        "full_rollup_ref": rollup.motion_rollup_ref,
    }
    assert len(artifact_rollup["motion_window_digests"]) == 3
    assert artifact_rollup["motion_window_digest_policy"] == {
        "artifact_cap": 3,
        "original_digest_count": 80,
        "truncated": True,
        "full_rollup_ref": rollup.motion_rollup_ref,
    }
    first_digest = artifact_rollup["motion_window_digests"][0]
    assert len(first_digest["dwpose_node_deltas"]) == 2
    assert len(first_digest["sway_metrics"]) == 2
    assert len(first_digest["phase_metrics"]) == 2
