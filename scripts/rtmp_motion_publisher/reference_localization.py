from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean
from typing import Any, Mapping


GLOBAL_RELOCK_MARGIN = 0.10
GLOBAL_RELOCK_CONFIRMATION_WINDOWS = 3
ORDERED_TRANSITION_CONFIRMATION_WINDOWS = 2
ORDERED_TRANSITION_MARGIN = 0.03
LOCAL_BACKTRACK_POINTS = 2
LOCAL_FORWARD_POINTS = 7
GLOBAL_RELOCK_HISTORY_SIZE = 3
PARTIAL_MATCH_THRESHOLD = 0.65


@dataclass(frozen=True)
class ReferencePoint:
    index: int
    chapter_id: str
    chapter_title: str
    chapter_start_ms: float
    chapter_end_ms: float
    match_role: str
    guidance_points: tuple[str, ...]
    features: dict[str, float]


FeatureSimilarity = Callable[
    [Mapping[str, float], Mapping[str, float], Mapping[str, float]],
    float,
]


class ReferenceSequenceLocalizer:
    """Own ordered progression, guarded transitions, and non-linear relocking."""

    def __init__(
        self,
        points: list[ReferencePoint],
        scales: Mapping[str, float],
        similarity: FeatureSimilarity,
    ) -> None:
        self.points = points
        self.scales = scales
        self._similarity = similarity
        self.previous_index: int | None = None
        self.pending_relock_chapter_id: str | None = None
        self.pending_relock_count = 0
        self.pending_transition_chapter_id: str | None = None
        self.pending_transition_count = 0

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

    def commit_selection(self, point_index: int, *, localization_ready: bool) -> None:
        if self.previous_index is not None or localization_ready:
            self.previous_index = point_index

    def select(
        self,
        history: list[dict[str, float]],
    ) -> tuple[ReferencePoint, float, dict[str, Any]]:
        sequence_scores = [
            self._sequence_score(point.index, history) for point in self.points
        ]
        full_sequence_index = max(
            range(len(self.points)),
            key=sequence_scores.__getitem__,
        )
        relock_history = history[-GLOBAL_RELOCK_HISTORY_SIZE:]
        relock_scores = [
            self._sequence_score(point.index, relock_history) for point in self.points
        ]
        global_index = max(range(len(self.points)), key=relock_scores.__getitem__)
        selected_index = full_sequence_index
        selection_mode = "global_initialization"
        local_index = full_sequence_index
        previous_chapter_index = full_sequence_index
        transition_supported = False
        if self.previous_index is not None:
            local_indexes = list(
                range(
                    max(0, self.previous_index - LOCAL_BACKTRACK_POINTS),
                    min(len(self.points), self.previous_index + LOCAL_FORWARD_POINTS),
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
                transition_supported = self._transition_supported(
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

            if (
                selection_mode == "ordered_local_prior"
                and self.points[selected_index].chapter_id == previous_chapter_id
                and full_sequence_chapter_id == previous_chapter_id
                and sequence_scores[full_sequence_index]
                >= sequence_scores[local_index] + 0.03
            ):
                selected_index = full_sequence_index
                selection_mode = "same_chapter_reposition"

            selected_chapter_id = self.points[selected_index].chapter_id
            relock_eligible = (
                not transition_supported
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
        )
        selected_score = (
            relock_scores[selected_index]
            if selection_mode == "confirmed_global_relock"
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
    ) -> bool:
        minimum = max(
            PARTIAL_MATCH_THRESHOLD,
            previous_chapter_score + ORDERED_TRANSITION_MARGIN,
        )
        return (
            full_sequence_chapter_id == local_chapter_id
            and full_sequence_score >= minimum
        ) or (global_chapter_id == local_chapter_id and global_score >= minimum)

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
        }


__all__ = [
    "GLOBAL_RELOCK_CONFIRMATION_WINDOWS",
    "GLOBAL_RELOCK_MARGIN",
    "ORDERED_TRANSITION_CONFIRMATION_WINDOWS",
    "ORDERED_TRANSITION_MARGIN",
    "PARTIAL_MATCH_THRESHOLD",
    "ReferencePoint",
    "ReferenceSequenceLocalizer",
]
