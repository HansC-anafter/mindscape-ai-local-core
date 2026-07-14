from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.reference_alignment import (  # noqa: E402
    LiveReferenceAlignmentMatcher,
    ORDERED_TRANSITION_CONFIRMATION_WINDOWS,
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


def _transition_profile() -> dict:
    profile = _profile()
    for chapter in profile["chapters"]:
        chapter["feature_series"] = chapter["feature_series"] * 2
    return profile


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
    features = _features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10)
    matcher.annotate(_summary(features))
    matcher.annotate(_summary(features))
    summary = _summary(
        features,
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
    exact = _features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10)
    matcher.annotate(_summary(exact))
    matcher.annotate(_summary(exact))
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


def test_opening_single_point_cannot_override_a_complete_matching_sequence() -> None:
    target_series = [
        _features(0.88, 0.88, 0.04, 0.03, 0.01, 0.12),
        _features(0.87, 0.89, 0.03, 0.02, 0.03, 0.13),
        _features(0.86, 0.91, 0.02, 0.01, 0.02, 0.14),
        _features(0.85, 0.92, 0.01, 0.01, 0.01, 0.15),
        _features(0.84, 0.93, 0.02, 0.01, 0.02, 0.16),
        _features(0.83, 0.94, 0.03, 0.02, 0.03, 0.17),
    ]
    profile = {
        "schema_version": "motion_reference_profile.v1",
        "reference_profile_id": "long-form-reference",
        "source_ref": "https://example.test/long-form-reference",
        "chapters": [
            {
                "chapter_id": "opening",
                "title": "Opening",
                "ts_start_ms": 0,
                "ts_end_ms": 12000,
                "match_role": "instruction",
                "feature_series": [
                    target_series[0],
                    *[_features(0.0, 0.0, 0.0, 0.0, 0.0, 1.0) for _ in range(5)],
                ],
            },
            {
                "chapter_id": "target",
                "title": "Target sequence",
                "ts_start_ms": 12000,
                "ts_end_ms": 30000,
                "match_role": "instruction",
                "feature_series": target_series,
            },
        ],
        "metadata": {"comparison_provenance": "independent_reference_asset"},
    }
    matcher = LiveReferenceAlignmentMatcher(profile)

    alignments = [matcher.annotate(_summary(features)) for features in target_series]

    assert alignments[0]["verdict"] == "insufficient_alignment"
    ready_alignments = [item for item in alignments if item["localization_ready"]]
    assert {item["chapter_id"] for item in ready_alignments} == {"target"}
    assert ready_alignments
    assert alignments[-1]["sequence_history_size"] == 6
    assert alignments[-1]["full_sequence_candidate_chapter_id"] == "target"
    assert alignments[-1]["localization_mode"].startswith("tempo_normalized_sequence")


def test_initialization_waits_for_sequence_evidence_before_setting_local_prior() -> None:
    matcher = LiveReferenceAlignmentMatcher(_profile())
    chapter_one = _features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10)

    first = matcher.annotate(_summary(chapter_one))
    second = matcher.annotate(_summary(chapter_one))

    assert first["localization_ready"] is False
    assert second["localization_ready"] is False
    assert matcher.localizer.previous_index is None

    third = matcher.annotate(_summary(chapter_one))

    assert third["localization_ready"] is True
    assert matcher.localizer.previous_index == third["reference_window_index"]


def test_cross_chapter_local_prior_is_rejected_when_sequence_evidence_disagrees() -> None:
    matcher = LiveReferenceAlignmentMatcher(_transition_profile())
    matcher.localizer.previous_index = 3
    full_history = [_features(0.9, 0.9, 0.1, 0.1, 0.1, 0.1)] * 6

    def score(endpoint: int, history: list[dict[str, float]]) -> float:
        if len(history) == 3:
            return {4: 0.76, 5: 0.74}.get(endpoint, 0.95 if endpoint == 0 else 0.2)
        return {3: 0.80, 4: 0.85, 5: 0.82}.get(endpoint, 0.96 if endpoint == 0 else 0.2)

    matcher.localizer._sequence_score = score  # type: ignore[method-assign]

    point, _, diagnostics = matcher.localizer.select(full_history)

    assert point.chapter_id == "chapter-one"
    assert diagnostics["local_candidate_chapter_id"] == "chapter-two"
    assert diagnostics["ordered_transition_supported"] is False
    assert diagnostics["selection_mode"] == "ordered_chapter_transition_rejected"


def test_supported_cross_chapter_transition_requires_consecutive_confirmation() -> None:
    matcher = LiveReferenceAlignmentMatcher(_transition_profile())
    matcher.localizer.previous_index = 3
    full_history = [_features(0.9, 0.9, 0.1, 0.1, 0.1, 0.1)] * 6

    def score(endpoint: int, history: list[dict[str, float]]) -> float:
        if len(history) == 3:
            return {4: 0.94, 5: 0.90}.get(endpoint, 0.2)
        return {3: 0.78, 4: 0.95, 5: 0.92}.get(endpoint, 0.2)

    matcher.localizer._sequence_score = score  # type: ignore[method-assign]

    first, _, first_diagnostics = matcher.localizer.select(full_history)
    second, _, second_diagnostics = matcher.localizer.select(full_history)

    assert ORDERED_TRANSITION_CONFIRMATION_WINDOWS == 2
    assert first.chapter_id == "chapter-one"
    assert first_diagnostics["selection_mode"] == "ordered_chapter_transition_pending"
    assert second.chapter_id == "chapter-two"
    assert second_diagnostics["selection_mode"] == "confirmed_ordered_chapter_transition"


def test_ordered_transition_rejects_reference_jump_faster_than_observed_time() -> None:
    matcher = LiveReferenceAlignmentMatcher(_transition_profile())
    matcher.localizer.previous_index = 3
    matcher.localizer.previous_observed_at_ms = 10_000.0
    full_history = [_features(0.9, 0.9, 0.1, 0.1, 0.1, 0.1)] * 6

    def score(endpoint: int, history: list[dict[str, float]]) -> float:
        if len(history) == 3:
            return 0.94 if endpoint == 6 else 0.2
        return {3: 0.80, 6: 0.95}.get(endpoint, 0.2)

    matcher.localizer._sequence_score = score  # type: ignore[method-assign]

    point, _, diagnostics = matcher.localizer.select(
        full_history,
        observed_at_ms=11_000.0,
    )

    assert point.chapter_id == "chapter-one"
    assert diagnostics["local_candidate_chapter_id"] == "chapter-one"
    assert diagnostics["ordered_transition_supported"] is False
    assert diagnostics["ordered_transition_local_forward_points"] == 3
    assert diagnostics["selection_mode"] == "global_relock_pending"


def test_established_paced_local_prior_remains_scoreable_when_global_candidate_differs() -> None:
    matcher = LiveReferenceAlignmentMatcher(_transition_profile())
    chapter_one = _features(0.90, 0.95, 0.02, 0.01, 0.02, 0.10)
    for start_ms in (0.0, 3_000.0, 6_000.0):
        summary = _summary(chapter_one)
        summary["ts_start_ms"] = start_ms
        matcher.annotate(summary)
    matcher.localizer.previous_index = 3
    matcher.localizer.previous_observed_at_ms = 6_000.0

    def score(endpoint: int, history: list[dict[str, float]]) -> float:
        if len(history) == 3:
            return 0.84 if endpoint == 6 else 0.2
        return {3: 0.78, 6: 0.83}.get(endpoint, 0.2)

    matcher.localizer._sequence_score = score  # type: ignore[method-assign]
    summary = _summary(chapter_one)
    summary["ts_start_ms"] = 9_000.0

    alignment = matcher.annotate(summary)

    assert alignment["chapter_id"] == "chapter-one"
    assert alignment["selection_mode"] == "ordered_local_prior"
    assert alignment["full_sequence_candidate_chapter_id"] == "chapter-two"
    assert alignment["established_local_prior"] is True
    assert alignment["localization_ready"] is True
