from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.reference_alignment import (  # noqa: E402
    LiveReferenceAlignmentMatcher,
)


def _features(
    pose: float,
    visibility: float,
    shoulder: float,
    hip: float,
    center: float,
    hold: float,
) -> dict[str, float]:
    return {
        "pose_confidence": pose,
        "body_visibility": visibility,
        "shoulder_line": shoulder,
        "hip_stack": hip,
        "center_stability": center,
        "hold_stability": hold,
    }


def _profile() -> dict:
    return {
        "schema_version": "motion_reference_profile.v1",
        "reference_profile_id": "reference-one",
        "source_ref": "https://example.test/reference",
        "chapters": [
            {
                "chapter_id": "chapter-one",
                "title": "Downward dog",
                "ts_start_ms": 0,
                "ts_end_ms": 12000,
                "match_role": "instruction",
                "feature_series": [
                    _features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10),
                    _features(0.92, 0.96, 0.03, 0.02, 0.03, 0.08),
                ],
                "guidance_points": ["alignment_confirmed"],
            },
            {
                "chapter_id": "chapter-two",
                "title": "Standing balance",
                "ts_start_ms": 12000,
                "ts_end_ms": 24000,
                "match_role": "instruction",
                "feature_series": [
                    _features(0.82, 0.86, 0.12, 0.08, 0.11, 0.22),
                    _features(0.80, 0.84, 0.14, 0.09, 0.12, 0.24),
                ],
                "guidance_points": ["shoulder_line_tilt"],
            },
        ],
        "metadata": {"comparison_provenance": "independent_reference_asset"},
    }


def _summary(features: dict[str, float], findings=None) -> dict:
    return {
        "window_id": "window-one",
        "confidence_stats": {
            "mean_confidence": features["pose_confidence"],
            "mean_visible_ratio": features["body_visibility"],
        },
        "scores": {
            "pose_confidence": features["pose_confidence"],
            "body_visibility": features["body_visibility"],
        },
        "findings": list(findings or []),
        "metadata": {
            "dwpose_node_deltas": [
                {"node_id": "shoulder_line", "delta_score": features["shoulder_line"]},
                {"node_id": "hip_stack", "delta_score": features["hip_stack"]},
            ],
            "sway_metrics": [
                {"axis": "center_stability", "delta_score": features["center_stability"]}
            ],
            "phase_metrics": [
                {"phase": "hold_stability", "delta_score": features["hold_stability"]}
            ],
        },
    }


def test_exact_window_emits_high_match_confirmation_and_not_absolute_findings() -> None:
    matcher = LiveReferenceAlignmentMatcher(_profile(), artifact_id="artifact-one")
    summary = _summary(
        _features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10),
        findings=["shoulder_line_tilt"],
    )

    alignment = matcher.annotate(summary)

    assert alignment["verdict"] == "high_match"
    assert alignment["chapter_id"] == "chapter-one"
    assert alignment["reference_profile_artifact_id"] == "artifact-one"
    assert summary["findings"] == []
    assert summary["metadata"]["observed_findings"] == ["shoulder_line_tilt"]
    assert summary["metadata"]["reference_guidance"]["kind"] == "confirmation"


def test_partial_match_emits_reference_delta_correction() -> None:
    matcher = LiveReferenceAlignmentMatcher(_profile())
    summary = _summary(_features(0.90, 0.95, 0.10, 0.01, 0.02, 0.10))

    alignment = matcher.annotate(summary)

    assert alignment["verdict"] == "partial_match"
    assert summary["findings"] == [
        "Match the reference by leveling your shoulder line."
    ]
    assert summary["metadata"]["reference_guidance"]["kind"] == "correction"


def test_sequence_can_relock_after_non_linear_reference_jump() -> None:
    matcher = LiveReferenceAlignmentMatcher(_profile())
    matcher.annotate(_summary(_features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10)))
    matcher.annotate(_summary(_features(0.92, 0.96, 0.03, 0.02, 0.03, 0.08)))

    alignment = matcher.annotate(
        _summary(_features(0.80, 0.84, 0.14, 0.09, 0.12, 0.24))
    )

    assert alignment["chapter_id"] == "chapter-two"
    assert alignment["localization_mode"].endswith("global_relock")
