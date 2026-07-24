from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean
from typing import Any, Mapping

from .reference_wrap_localization import (
    CyclicWrapCandidate,
    best_cyclic_wrap_candidate,
)


GLOBAL_RELOCK_MARGIN = 0.10
GLOBAL_RELOCK_CONFIRMATION_WINDOWS = 3
ORDERED_TRANSITION_CONFIRMATION_WINDOWS = 2
ORDERED_TRANSITION_MARGIN = 0.03
ORDERED_TRANSITION_CONFLICT_TOLERANCE = 0.02
LOCAL_BACKTRACK_POINTS = 2
LOCAL_FORWARD_POINTS = 7
LOCAL_MIN_FORWARD_POINTS = 3
MAX_ORDERED_TEMPO_RATIO = 2.0
GLOBAL_RELOCK_HISTORY_SIZE = 3
PARTIAL_MATCH_THRESHOLD = 0.65
SAME_CHAPTER_WRAP_CONFIRMATION_WINDOWS = 2
SAME_CHAPTER_WRAP_MARGIN = 0.05
SAME_CHAPTER_WRAP_EDGE_FRACTION = 0.35
SAME_CHAPTER_WRAP_MIN_BACKTRACK_POINTS = 3


@dataclass(frozen=True)
class ReferencePoint:
    index: int
    chapter_id: str
    chapter_title: str
    chapter_start_ms: float
    chapter_end_ms: float
    reference_time_ms: float
    match_role: str
    guidance_points: tuple[str, ...]
    features: dict[str, float]


FeatureSimilarity = Callable[
    [Mapping[str, float], Mapping[str, float], Mapping[str, float]],
    float,
]
SimilarityMatrix = Callable[
    [list[dict[str, float]]],
    list[list[float]],
]


class ReferenceSequenceLocalizer:
    """Own ordered progression, guarded transitions, and non-linear relocking."""

    def __init__(
        self,
        points: list[ReferencePoint],
        scales: Mapping[str, float],
        similarity: FeatureSimilarity,
        similarity_matrix: SimilarityMatrix | None = None,
    ) -> None:
        self.points = points
        self.scales = scales
        self._similarity = similarity
        self._similarity_matrix = similarity_matrix
        self.previous_index: int | None = None
        self.pending_relock_chapter_id: str | None = None
        self.pending_relock_count = 0
        self.pending_transition_chapter_id: str | None = None
        self.pending_transition_count = 0
        self.pending_wrap_chapter_id: str | None = None
        self.pending_wrap_count = 0
        self.previous_observed_at_ms: float | None = None
        self._active_similarity_history: list[dict[str, float]] | None = None
        self._active_similarity_rows: list[list[float]] | None = None
        self.chapter_point_bounds = self._chapter_point_bounds(points)

    @staticmethod
    def _chapter_point_bounds(
        points: list[ReferencePoint],
    ) -> dict[str, tuple[int, int]]:
        bounds: dict[str, tuple[int, int]] = {}
        for point in points:
            first, _last = bounds.get(point.chapter_id, (point.index, point.index))
            bounds[point.chapter_id] = (first, point.index)
        return bounds

    def _similarity_rows(
        self,
        history: list[dict[str, float]],
    ) -> list[list[float]]:
        if self._similarity_matrix is not None:
            return self._similarity_matrix(history)
        return [
            [
                self._similarity(point.features, features, self.scales)
                for point in self.points
            ]
            for features in history
        ]

    def _sequence_score(
        self,
        endpoint: int,
        history: list[dict[str, float]],
    ) -> float:
        count = len(history)
        if count <= 0:
            return 0.0
        max_span = min(endpoint + 1, count * 2)
        span_lengths = {
            min(max_span, max(1, count // 2)),
            min(max_span, count),
            max_span,
        }
        scores: list[float] = []
        for span_length in span_lengths:
            reference = self.points[endpoint - span_length + 1 : endpoint + 1]
            if count == 1 or len(reference) == 1:
                sampled = [reference[0]] * count
            else:
                sampled = [
                    reference[round(index * (len(reference) - 1) / (count - 1))]
                    for index in range(count)
                ]
            if (
                history is self._active_similarity_history
                and self._active_similarity_rows is not None
            ):
                scores.append(
                    mean(
                        self._active_similarity_rows[index][point.index]
                        for index, point in enumerate(sampled)
                    )
                )
            else:
                scores.append(
                    mean(
                        self._similarity(point.features, features, self.scales)
                        for point, features in zip(sampled, history)
                    )
                )
        return max(scores)

    def _reset_pending_relock(self) -> None:
        self.pending_relock_chapter_id = None
        self.pending_relock_count = 0

    def _track_pending_relock(self, chapter_id: str) -> int:
        if chapter_id == self.pending_relock_chapter_id:
            self.pending_relock_count += 1
        else:
            self.pending_relock_chapter_id = chapter_id
            self.pending_relock_count = 1
        return self.pending_relock_count

    def _reset_pending_transition(self) -> None:
        self.pending_transition_chapter_id = None
        self.pending_transition_count = 0

    def _track_pending_transition(self, chapter_id: str) -> int:
        if chapter_id == self.pending_transition_chapter_id:
            self.pending_transition_count += 1
        else:
            self.pending_transition_chapter_id = chapter_id
            self.pending_transition_count = 1
        return self.pending_transition_count

    def _reset_pending_wrap(self) -> None:
        self.pending_wrap_chapter_id = None
        self.pending_wrap_count = 0

    def _track_pending_wrap(self, chapter_id: str) -> int:
        if chapter_id == self.pending_wrap_chapter_id:
            self.pending_wrap_count += 1
        else:
            self.pending_wrap_chapter_id = chapter_id
            self.pending_wrap_count = 1
        return self.pending_wrap_count

    def _same_chapter_wrap_eligible(
        self,
        *,
        chapter_id: str,
        candidate_index: int,
        candidate_score: float,
        selected_index: int,
        selected_score: float,
    ) -> bool:
        if self.previous_index is None:
            return False
        first_index, last_index = self.chapter_point_bounds[chapter_id]
        span = last_index - first_index
        if span < SAME_CHAPTER_WRAP_MIN_BACKTRACK_POINTS:
            return False
        trailing_edge = first_index + math.ceil(
            span * (1.0 - SAME_CHAPTER_WRAP_EDGE_FRACTION)
        )
        leading_edge = first_index + math.floor(
            span * SAME_CHAPTER_WRAP_EDGE_FRACTION
        )
        minimum_backtrack = max(
            SAME_CHAPTER_WRAP_MIN_BACKTRACK_POINTS,
            math.ceil(span * 0.4),
        )
        return (
            self.previous_index >= trailing_edge
            and candidate_index <= leading_edge
            and self.previous_index - candidate_index >= minimum_backtrack
            and selected_index >= candidate_index
            and candidate_score
            >= max(PARTIAL_MATCH_THRESHOLD, selected_score + SAME_CHAPTER_WRAP_MARGIN)
        )

    def commit_selection(
        self,
        point_index: int,
        *,
        localization_ready: bool,
        observed_at_ms: float | None = None,
    ) -> None:
        if self.previous_index is not None or localization_ready:
            self.previous_index = point_index
            if observed_at_ms is not None:
                self.previous_observed_at_ms = observed_at_ms

    def _local_forward_points(self, observed_at_ms: float | None) -> int:
        if (
            self.previous_index is None
            or self.previous_observed_at_ms is None
            or observed_at_ms is None
            or observed_at_ms <= self.previous_observed_at_ms
        ):
            return LOCAL_FORWARD_POINTS
        previous_point = self.points[self.previous_index]
        cadence_ms = 0.0
        if self.previous_index + 1 < len(self.points):
            next_point = self.points[self.previous_index + 1]
            if next_point.chapter_id == previous_point.chapter_id:
                cadence_ms = next_point.reference_time_ms - previous_point.reference_time_ms
        if cadence_ms <= 0 and self.previous_index > 0:
            prior_point = self.points[self.previous_index - 1]
            if prior_point.chapter_id == previous_point.chapter_id:
                cadence_ms = previous_point.reference_time_ms - prior_point.reference_time_ms
        cadence_ms = max(1.0, cadence_ms)
        observed_elapsed_ms = observed_at_ms - self.previous_observed_at_ms
        paced_points = math.ceil(
            observed_elapsed_ms * MAX_ORDERED_TEMPO_RATIO / cadence_ms
        )
        return min(
            LOCAL_FORWARD_POINTS,
            max(LOCAL_MIN_FORWARD_POINTS, paced_points + 1),
        )

    def select(
        self,
        history: list[dict[str, float]],
        *,
        observed_at_ms: float | None = None,
    ) -> tuple[ReferencePoint, float, dict[str, Any]]:
        similarity_rows = self._similarity_rows(history)
        self._active_similarity_history = history
        self._active_similarity_rows = similarity_rows
        sequence_scores = [
            self._sequence_score(point.index, history) for point in self.points
        ]
        full_sequence_index = max(
            range(len(self.points)),
            key=sequence_scores.__getitem__,
        )
        relock_history = history[-GLOBAL_RELOCK_HISTORY_SIZE:]
        self._active_similarity_history = relock_history
        self._active_similarity_rows = similarity_rows[-len(relock_history) :]
        relock_scores = [
            self._sequence_score(point.index, relock_history) for point in self.points
        ]
        self._active_similarity_history = None
        self._active_similarity_rows = None
        global_index = max(range(len(self.points)), key=relock_scores.__getitem__)
        cyclic_wrap_candidate: CyclicWrapCandidate | None = None
        selected_index = full_sequence_index
        selection_mode = "global_initialization"
        local_index = full_sequence_index
        previous_chapter_index = full_sequence_index
        transition_supported = False
        transition_evidence_conflicted = False
        local_forward_points = LOCAL_FORWARD_POINTS
        if self.previous_index is not None:
            local_forward_points = self._local_forward_points(observed_at_ms)
            local_indexes = list(
                range(
                    max(0, self.previous_index - LOCAL_BACKTRACK_POINTS),
                    min(len(self.points), self.previous_index + local_forward_points),
                )
            ) or [full_sequence_index]
            local_index = max(local_indexes, key=sequence_scores.__getitem__)
            previous_chapter_id = self.points[self.previous_index].chapter_id
            local_chapter_id = self.points[local_index].chapter_id
            global_chapter_id = self.points[global_index].chapter_id
            full_sequence_chapter_id = self.points[full_sequence_index].chapter_id
            previous_chapter_indexes = [
                index
                for index in local_indexes
                if self.points[index].chapter_id == previous_chapter_id
            ]
            previous_chapter_index = max(
                previous_chapter_indexes or [self.previous_index],
                key=sequence_scores.__getitem__,
            )
            previous_chapter_score = sequence_scores[previous_chapter_index]
            selected_index = local_index
            selection_mode = "ordered_local_prior"

            if local_chapter_id != previous_chapter_id:
                (
                    transition_supported,
                    transition_evidence_conflicted,
                ) = self._transition_supported(
                    local_chapter_id=local_chapter_id,
                    full_sequence_chapter_id=full_sequence_chapter_id,
                    full_sequence_score=sequence_scores[full_sequence_index],
                    global_chapter_id=global_chapter_id,
                    global_score=relock_scores[global_index],
                    previous_chapter_score=previous_chapter_score,
                )
                selected_index = previous_chapter_index
                if transition_supported:
                    confirmation_count = self._track_pending_transition(
                        local_chapter_id
                    )
                    if confirmation_count >= ORDERED_TRANSITION_CONFIRMATION_WINDOWS:
                        selected_index = local_index
                        selection_mode = "confirmed_ordered_chapter_transition"
                        self._reset_pending_transition()
                        self._reset_pending_relock()
                    else:
                        selection_mode = "ordered_chapter_transition_pending"
                else:
                    self._reset_pending_transition()
                    selection_mode = "ordered_chapter_transition_rejected"
            else:
                self._reset_pending_transition()

            if global_chapter_id != previous_chapter_id:
                cyclic_wrap_candidate = best_cyclic_wrap_candidate(
                    points=self.points,
                    chapter_bounds=self.chapter_point_bounds[previous_chapter_id],
                    previous_index=self.previous_index,
                    similarity_rows=similarity_rows,
                    edge_fraction=SAME_CHAPTER_WRAP_EDGE_FRACTION,
                    minimum_backtrack_points=(
                        SAME_CHAPTER_WRAP_MIN_BACKTRACK_POINTS
                    ),
                    minimum_cyclic_advantage=SAME_CHAPTER_WRAP_MARGIN,
                )

            if (
                selection_mode == "ordered_local_prior"
                and self.points[selected_index].chapter_id == previous_chapter_id
                and full_sequence_chapter_id == previous_chapter_id
                and sequence_scores[full_sequence_index]
                >= sequence_scores[local_index] + 0.03
                and full_sequence_index
                >= self.previous_index - LOCAL_BACKTRACK_POINTS
            ):
                selected_index = full_sequence_index
                selection_mode = "same_chapter_reposition"

            wrap_candidate_index = (
                cyclic_wrap_candidate.index
                if cyclic_wrap_candidate is not None
                else global_index
            )
            wrap_candidate_score = (
                cyclic_wrap_candidate.score
                if cyclic_wrap_candidate is not None
                else relock_scores[global_index]
            )
            wrap_candidate_chapter_id = self.points[
                wrap_candidate_index
            ].chapter_id
            same_chapter_wrap_eligible = (
                (
                    selection_mode == "ordered_local_prior"
                    or (
                        selection_mode == "ordered_chapter_transition_rejected"
                        and cyclic_wrap_candidate is not None
                    )
                )
                and wrap_candidate_chapter_id == previous_chapter_id
                and self._same_chapter_wrap_eligible(
                    chapter_id=previous_chapter_id,
                    candidate_index=wrap_candidate_index,
                    candidate_score=wrap_candidate_score,
                    selected_index=selected_index,
                    selected_score=sequence_scores[selected_index],
                )
            )
            if same_chapter_wrap_eligible:
                confirmation_count = self._track_pending_wrap(previous_chapter_id)
                if confirmation_count >= SAME_CHAPTER_WRAP_CONFIRMATION_WINDOWS:
                    selected_index = wrap_candidate_index
                    selection_mode = "confirmed_same_chapter_wrap"
                    self._reset_pending_wrap()
                    self._reset_pending_relock()
                    self._reset_pending_transition()
                else:
                    selection_mode = "same_chapter_wrap_pending"
            elif selection_mode != "confirmed_same_chapter_wrap":
                self._reset_pending_wrap()

            selected_chapter_id = self.points[selected_index].chapter_id
            relock_eligible = (
                not transition_supported
                and not same_chapter_wrap_eligible
                and selection_mode != "confirmed_ordered_chapter_transition"
                and selected_chapter_id == previous_chapter_id
                and global_chapter_id != previous_chapter_id
                and relock_scores[global_index]
                >= max(
                    PARTIAL_MATCH_THRESHOLD,
                    sequence_scores[selected_index] + GLOBAL_RELOCK_MARGIN,
                )
            )
            if relock_eligible:
                confirmation_count = self._track_pending_relock(global_chapter_id)
                if confirmation_count >= GLOBAL_RELOCK_CONFIRMATION_WINDOWS:
                    selected_index = global_index
                    selection_mode = "confirmed_global_relock"
                    self._reset_pending_relock()
                else:
                    selection_mode = "global_relock_pending"
            elif selection_mode != "confirmed_ordered_chapter_transition":
                self._reset_pending_relock()

        diagnostics = self._diagnostics(
            sequence_scores=sequence_scores,
            relock_scores=relock_scores,
            selection_mode=selection_mode,
            global_index=global_index,
            full_sequence_index=full_sequence_index,
            local_index=local_index,
            previous_chapter_index=previous_chapter_index,
            transition_supported=transition_supported,
            transition_evidence_conflicted=transition_evidence_conflicted,
            local_forward_points=local_forward_points,
            cyclic_wrap_candidate=cyclic_wrap_candidate,
        )
        selected_score = (
            (
                cyclic_wrap_candidate.score
                if selection_mode == "confirmed_same_chapter_wrap"
                and cyclic_wrap_candidate is not None
                else relock_scores[selected_index]
            )
            if selection_mode
            in {"confirmed_global_relock", "confirmed_same_chapter_wrap"}
            else sequence_scores[selected_index]
        )
        return self.points[selected_index], selected_score, diagnostics

    @staticmethod
    def _transition_supported(
        *,
        local_chapter_id: str,
        full_sequence_chapter_id: str,
        full_sequence_score: float,
        global_chapter_id: str,
        global_score: float,
        previous_chapter_score: float,
    ) -> tuple[bool, bool]:
        minimum = max(
            PARTIAL_MATCH_THRESHOLD,
            previous_chapter_score + ORDERED_TRANSITION_MARGIN,
        )
        full_sequence_supports_transition = (
            full_sequence_chapter_id == local_chapter_id
            and full_sequence_score >= minimum
        )
        global_supports_transition = (
            global_chapter_id == local_chapter_id and global_score >= minimum
        )
        evidence_conflicted = (
            full_sequence_supports_transition
            and global_chapter_id != local_chapter_id
            and global_score
            > full_sequence_score + ORDERED_TRANSITION_CONFLICT_TOLERANCE
        )
        return (
            (full_sequence_supports_transition or global_supports_transition)
            and not evidence_conflicted,
            evidence_conflicted,
        )

    def _diagnostics(
        self,
        *,
        sequence_scores: list[float],
        relock_scores: list[float],
        selection_mode: str,
        global_index: int,
        full_sequence_index: int,
        local_index: int,
        previous_chapter_index: int,
        transition_supported: bool,
        transition_evidence_conflicted: bool,
        local_forward_points: int,
        cyclic_wrap_candidate: CyclicWrapCandidate | None,
    ) -> dict[str, Any]:
        return {
            "selection_mode": selection_mode,
            "global_candidate_chapter_id": self.points[global_index].chapter_id,
            "global_candidate_window_index": global_index,
            "global_candidate_score": round(relock_scores[global_index], 4),
            "full_sequence_candidate_chapter_id": self.points[
                full_sequence_index
            ].chapter_id,
            "full_sequence_candidate_window_index": full_sequence_index,
            "full_sequence_candidate_score": round(
                sequence_scores[full_sequence_index], 4
            ),
            "local_candidate_chapter_id": self.points[local_index].chapter_id,
            "local_candidate_window_index": local_index,
            "local_candidate_score": round(sequence_scores[local_index], 4),
            "previous_chapter_candidate_chapter_id": self.points[
                previous_chapter_index
            ].chapter_id,
            "previous_chapter_candidate_window_index": previous_chapter_index,
            "previous_chapter_candidate_score": round(
                sequence_scores[previous_chapter_index], 4
            ),
            "ordered_transition_supported": transition_supported,
            "ordered_transition_evidence_conflicted": (
                transition_evidence_conflicted
            ),
            "ordered_transition_conflict_tolerance": (
                ORDERED_TRANSITION_CONFLICT_TOLERANCE
            ),
            "ordered_transition_local_forward_points": local_forward_points,
            "ordered_transition_max_tempo_ratio": MAX_ORDERED_TEMPO_RATIO,
            "pending_transition_chapter_id": self.pending_transition_chapter_id,
            "pending_transition_count": self.pending_transition_count,
            "ordered_transition_confirmation_windows": (
                ORDERED_TRANSITION_CONFIRMATION_WINDOWS
            ),
            "ordered_transition_margin": ORDERED_TRANSITION_MARGIN,
            "pending_relock_chapter_id": self.pending_relock_chapter_id,
            "pending_relock_count": self.pending_relock_count,
            "relock_confirmation_windows": GLOBAL_RELOCK_CONFIRMATION_WINDOWS,
            "relock_margin": GLOBAL_RELOCK_MARGIN,
            "pending_same_chapter_wrap_chapter_id": self.pending_wrap_chapter_id,
            "pending_same_chapter_wrap_count": self.pending_wrap_count,
            "same_chapter_wrap_confirmation_windows": (
                SAME_CHAPTER_WRAP_CONFIRMATION_WINDOWS
            ),
            "same_chapter_wrap_margin": SAME_CHAPTER_WRAP_MARGIN,
            "same_chapter_wrap_edge_fraction": SAME_CHAPTER_WRAP_EDGE_FRACTION,
            "cyclic_wrap_candidate_window_index": (
                cyclic_wrap_candidate.index
                if cyclic_wrap_candidate is not None
                else None
            ),
            "cyclic_wrap_candidate_score": (
                round(cyclic_wrap_candidate.score, 4)
                if cyclic_wrap_candidate is not None
                else None
            ),
            "cyclic_wrap_candidate_span_length": (
                cyclic_wrap_candidate.span_length
                if cyclic_wrap_candidate is not None
                else None
            ),
            "cyclic_wrap_candidate_linear_baseline_score": (
                round(cyclic_wrap_candidate.linear_baseline_score, 4)
                if cyclic_wrap_candidate is not None
                else None
            ),
        }


__all__ = [
    "GLOBAL_RELOCK_CONFIRMATION_WINDOWS",
    "GLOBAL_RELOCK_MARGIN",
    "ORDERED_TRANSITION_CONFIRMATION_WINDOWS",
    "ORDERED_TRANSITION_CONFLICT_TOLERANCE",
    "ORDERED_TRANSITION_MARGIN",
    "PARTIAL_MATCH_THRESHOLD",
    "ReferencePoint",
    "ReferenceSequenceLocalizer",
]
