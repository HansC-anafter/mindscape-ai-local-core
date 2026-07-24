from __future__ import annotations

import math
from collections import deque
from statistics import mean
from typing import Any, Mapping

from .reference_profile import compact_window_features
from .reference_guidance_gate import (
    CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS,
    ReferenceGuidanceGate,
)
from .reference_localization import (
    GLOBAL_RELOCK_CONFIRMATION_WINDOWS,
    GLOBAL_RELOCK_MARGIN,
    ORDERED_TRANSITION_CONFIRMATION_WINDOWS,
    ORDERED_TRANSITION_MARGIN,
    PARTIAL_MATCH_THRESHOLD,
    SAME_CHAPTER_WRAP_CONFIRMATION_WINDOWS,
    ReferencePoint,
    ReferenceSequenceLocalizer,
)
from .reference_similarity import VectorizedReferenceSimilarityMatrix


HISTORY_SIZE = 6
HIGH_MATCH_THRESHOLD = 0.84
MIN_LOCALIZATION_HISTORY = 3
LOCALIZATION_CONFLICT_TOLERANCE = 0.02


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _feature_scale(key: str, values: list[float]) -> float:
    minimums = {
        "pose_confidence": 0.10,
        "body_visibility": 0.10,
        "shoulder_line": 0.05,
        "hip_stack": 0.05,
        "center_stability": 0.04,
        "hold_stability": 0.10,
    }
    spread = _percentile(values, 0.90) - _percentile(values, 0.10)
    return max(minimums.get(key, 0.05), spread)


def _feature_similarity(
    reference: Mapping[str, float],
    learner: Mapping[str, float],
    scales: Mapping[str, float],
) -> float:
    common = sorted(set(reference).intersection(learner))
    if not common:
        return 0.0
    distances = [
        min(
            3.0,
            abs(_number(learner[key]) - _number(reference[key]))
            / max(0.001, _number(scales.get(key), 0.05)),
        )
        for key in common
    ]
    root_mean_square = math.sqrt(mean(distance * distance for distance in distances))
    return max(0.0, min(1.0, math.exp(-root_mean_square)))


def _correction_text(feature_key: str) -> str:
    return {
        "pose_confidence": "Keep your full body visible before continuing the movement.",
        "body_visibility": "Keep your full body visible before continuing the movement.",
        "shoulder_line": "Match the reference by leveling your shoulder line.",
        "hip_stack": "Match the reference by stacking the pelvis more evenly.",
        "center_stability": "Reduce center-line sway and settle before the next transition.",
        "hold_stability": "Hold the current shape more steadily before moving on.",
    }.get(feature_key, "Adjust this shape toward the selected reference segment.")


def _localization_evidence_conflicted(
    *,
    chapter_id: str,
    selected_score: float,
    localization: Mapping[str, Any],
) -> bool:
    for prefix in ("full_sequence_candidate", "global_candidate"):
        candidate_chapter_id = str(
            localization.get(f"{prefix}_chapter_id") or ""
        ).strip()
        candidate_score = _number(localization.get(f"{prefix}_score"))
        if (
            candidate_chapter_id
            and candidate_chapter_id != chapter_id
            and candidate_score > selected_score + LOCALIZATION_CONFLICT_TOLERANCE
        ):
            return True
    return False


class LiveReferenceAlignmentMatcher:
    """Locate compact live windows in a profile without fixed-duration slicing."""

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        artifact_id: str = "",
    ) -> None:
        self.profile = dict(profile)
        self.profile_id = str(profile.get("reference_profile_id") or "").strip()
        self.source_ref = str(profile.get("source_ref") or "").strip() or None
        self.artifact_id = artifact_id.strip() or None
        self.provenance = str(
            _record(profile.get("metadata")).get("comparison_provenance") or ""
        ).strip()
        self.points = self._flatten_points(profile)
        if not self.points:
            raise ValueError("motion_reference_profile_features_missing")
        buckets: dict[str, list[float]] = {}
        for point in self.points:
            for key, value in point.features.items():
                buckets.setdefault(key, []).append(value)
        self.scales = {key: _feature_scale(key, values) for key, values in buckets.items()}
        self.history: deque[dict[str, float]] = deque(maxlen=HISTORY_SIZE)
        self.chapter_point_bounds = self._chapter_point_bounds(self.points)
        self.guidance_gate = ReferenceGuidanceGate()
        self.localizer = ReferenceSequenceLocalizer(
            self.points,
            self.scales,
            _feature_similarity,
            similarity_matrix=VectorizedReferenceSimilarityMatrix(
                self.points,
                self.scales,
            ),
        )

    @staticmethod
    def _chapter_point_bounds(
        points: list[ReferencePoint],
    ) -> dict[str, tuple[int, int]]:
        bounds: dict[str, tuple[int, int]] = {}
        for point in points:
            first, _last = bounds.get(point.chapter_id, (point.index, point.index))
            bounds[point.chapter_id] = (first, point.index)
        return bounds

    @staticmethod
    def _flatten_points(profile: Mapping[str, Any]) -> list[ReferencePoint]:
        points: list[ReferencePoint] = []
        chapters = profile.get("chapters")
        if not isinstance(chapters, list):
            return points
        for chapter in chapters:
            if not isinstance(chapter, Mapping):
                continue
            chapter_id = str(chapter.get("chapter_id") or "").strip()
            if not chapter_id:
                continue
            title = str(chapter.get("title") or chapter_id).strip()
            guidance_points = tuple(
                str(item).strip()
                for item in list(chapter.get("guidance_points") or [])[:8]
                if str(item).strip()
            )
            series = chapter.get("feature_series")
            if not isinstance(series, list):
                continue
            chapter_start_ms = max(0.0, _number(chapter.get("ts_start_ms")))
            chapter_end_ms = max(0.0, _number(chapter.get("ts_end_ms")))
            for series_index, raw_features in enumerate(series):
                if not isinstance(raw_features, Mapping):
                    continue
                features = {
                    str(key): _number(value)
                    for key, value in raw_features.items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
                if not features:
                    continue
                points.append(
                    ReferencePoint(
                        index=len(points),
                        chapter_id=chapter_id,
                        chapter_title=title,
                        chapter_start_ms=chapter_start_ms,
                        chapter_end_ms=chapter_end_ms,
                        reference_time_ms=(
                            chapter_start_ms
                            if len(series) <= 1
                            else chapter_start_ms
                            + (chapter_end_ms - chapter_start_ms)
                            * series_index
                            / (len(series) - 1)
                        ),
                        match_role=str(chapter.get("match_role") or "instruction"),
                        guidance_points=guidance_points,
                        features=features,
                    )
                )
        return points

    def annotate(self, summary: dict[str, Any]) -> dict[str, Any]:
        learner_features = compact_window_features(summary)
        self.history.append(learner_features)
        observed_at_ms = (
            _number(summary.get("ts_start_ms"))
            if summary.get("ts_start_ms") is not None
            else None
        )
        point, score, localization = self.localizer.select(
            list(self.history),
            observed_at_ms=observed_at_ms,
        )
        previous_index = self.localizer.previous_index
        confidence_stats = _record(summary.get("confidence_stats"))
        pose_confidence = _number(confidence_stats.get("mean_confidence"))
        pose_match_score = _feature_similarity(
            point.features,
            learner_features,
            self.scales,
        )
        alignment_confidence = max(
            0.0,
            min(1.0, min(score, pose_match_score) * pose_confidence),
        )
        selection_mode = str(localization.get("selection_mode") or "")
        established_local_prior = (
            previous_index is not None
            and selection_mode == "ordered_local_prior"
            and point.chapter_id == self.points[previous_index].chapter_id
            and score >= PARTIAL_MATCH_THRESHOLD
        )
        confirmed_selection = selection_mode in {
            "confirmed_global_relock",
            "confirmed_ordered_chapter_transition",
            "confirmed_same_chapter_wrap",
        }
        localization_evidence_conflicted = (
            not confirmed_selection
            and _localization_evidence_conflicted(
                chapter_id=point.chapter_id,
                selected_score=score,
                localization=localization,
            )
        )
        sequence_supported = (
            point.chapter_id
            == localization.get("full_sequence_candidate_chapter_id")
            or established_local_prior
        )
        base_localization_ready = (
            len(self.history) >= MIN_LOCALIZATION_HISTORY
            and (
                confirmed_selection
                or (sequence_supported and not localization_evidence_conflicted)
            )
        )
        guidance_gate = self.guidance_gate.observe(
            point.chapter_id,
            localization_ready=base_localization_ready,
        )
        localization_ready = base_localization_ready and guidance_gate.ready
        if len(self.history) < MIN_LOCALIZATION_HISTORY:
            localization_ready_reason = "insufficient_history"
        elif base_localization_ready and not guidance_gate.ready:
            localization_ready_reason = "chapter_guidance_confirmation_pending"
        elif confirmed_selection:
            localization_ready_reason = selection_mode
        elif localization_evidence_conflicted:
            localization_ready_reason = "multiscale_evidence_conflict"
        elif sequence_supported:
            localization_ready_reason = "sequence_supported"
        else:
            localization_ready_reason = "sequence_evidence_pending"
        self.localizer.commit_selection(
            point.index,
            localization_ready=localization_ready,
            observed_at_ms=observed_at_ms,
        )
        if not localization_ready:
            verdict = "insufficient_alignment"
        elif pose_match_score >= HIGH_MATCH_THRESHOLD:
            verdict = "high_match"
        elif pose_match_score >= PARTIAL_MATCH_THRESHOLD:
            verdict = "partial_match"
        else:
            verdict = "insufficient_alignment"

        common_keys = sorted(set(point.features).intersection(learner_features))
        deltas = [
            {
                "feature": key,
                "reference": round(point.features[key], 4),
                "learner": round(learner_features[key], 4),
                "difference": round(learner_features[key] - point.features[key], 4),
                "normalized_distance": round(
                    abs(learner_features[key] - point.features[key])
                    / max(0.001, self.scales[key]),
                    4,
                ),
            }
            for key in common_keys
        ]
        deltas.sort(key=lambda item: item["normalized_distance"], reverse=True)
        corrections: list[str] = []
        if verdict == "partial_match" and point.match_role == "instruction":
            for delta in deltas:
                if delta["normalized_distance"] < 0.55:
                    continue
                correction = _correction_text(str(delta["feature"]))
                if correction not in corrections:
                    corrections.append(correction)
                if len(corrections) >= 2:
                    break

        metadata = _record(summary.get("metadata"))
        observed_findings = [
            str(item)
            for item in list(summary.get("findings") or [])
            if str(item).strip()
        ]
        alignment = {
            "schema_version": "live_reference_alignment.v1",
            "reference_profile_id": self.profile_id,
            "reference_profile_artifact_id": self.artifact_id,
            "reference_source_ref": self.source_ref,
            "comparison_provenance": self.provenance,
            "chapter_id": point.chapter_id,
            "chapter_title": point.chapter_title,
            "chapter_ts_start_ms": point.chapter_start_ms,
            "chapter_ts_end_ms": point.chapter_end_ms,
            "match_role": point.match_role,
            "reference_window_index": point.index,
            "reference_time_ms": round(point.reference_time_ms, 3),
            "chapter_reference_window_start_index": self.chapter_point_bounds[
                point.chapter_id
            ][0],
            "chapter_reference_window_end_index": self.chapter_point_bounds[
                point.chapter_id
            ][1],
            "previous_reference_window_index": previous_index,
            "score": round(pose_match_score, 4),
            "localization_score": round(score, 4),
            "confidence": round(alignment_confidence, 4),
            "verdict": verdict,
            "feature_deltas": deltas[:8],
            "guidance_points": list(point.guidance_points),
            "sequence_history_size": len(self.history),
            "localization_ready": localization_ready,
            "localization_ready_reason": localization_ready_reason,
            "base_localization_ready": base_localization_ready,
            "localization_evidence_conflicted": localization_evidence_conflicted,
            "localization_conflict_tolerance": LOCALIZATION_CONFLICT_TOLERANCE,
            "guidance_chapter_committed_id": (
                guidance_gate.committed_chapter_id
            ),
            "guidance_chapter_pending_id": guidance_gate.pending_chapter_id,
            "guidance_chapter_pending_count": guidance_gate.pending_count,
            "guidance_chapter_confirmation_windows": (
                CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS
            ),
            "established_local_prior": established_local_prior,
            "minimum_localization_history": MIN_LOCALIZATION_HISTORY,
            "localization_mode": (
                "tempo_normalized_sequence_with_confirmed_transitions_wrap_and_global_relock"
            ),
            **localization,
        }
        if point.match_role != "instruction":
            guidance_cue = {"kind": "suppressed", "reason": "reference_context_segment"}
            corrections = []
        elif corrections:
            guidance_cue = {
                "kind": "correction",
                "key": f"reference:{point.chapter_id}:{corrections[0]}",
                "text": corrections[0],
                "priority": "correction",
            }
        elif verdict == "high_match":
            guidance_cue = {
                "kind": "confirmation",
                "key": f"reference:{point.chapter_id}:aligned",
                "text": f"Movement matches the reference chapter: {point.chapter_title}.",
                "priority": "info",
            }
        else:
            guidance_cue = {
                "kind": "warning",
                "key": "reference:reacquire",
                "text": "Hold briefly so the coach can reacquire the reference sequence.",
                "priority": "warning",
            }
        metadata["observed_findings"] = observed_findings
        metadata["reference_alignment"] = alignment
        metadata["reference_guidance"] = guidance_cue
        summary["metadata"] = metadata
        summary["findings"] = corrections
        return alignment


__all__ = [
    "CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS",
    "HIGH_MATCH_THRESHOLD",
    "LOCALIZATION_CONFLICT_TOLERANCE",
    "GLOBAL_RELOCK_CONFIRMATION_WINDOWS",
    "GLOBAL_RELOCK_MARGIN",
    "LiveReferenceAlignmentMatcher",
    "ORDERED_TRANSITION_CONFIRMATION_WINDOWS",
    "ORDERED_TRANSITION_MARGIN",
    "PARTIAL_MATCH_THRESHOLD",
    "SAME_CHAPTER_WRAP_CONFIRMATION_WINDOWS",
]
