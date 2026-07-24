from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.reference_wrap_localization import (  # noqa: E402
    best_cyclic_wrap_candidate,
)
from rtmp_motion_publisher.reference_localization import (  # noqa: E402
    ReferencePoint,
    ReferenceSequenceLocalizer,
)


@dataclass(frozen=True)
class _Point:
    index: int
    chapter_id: str


def test_cyclic_candidate_scores_chapter_tail_followed_by_chapter_head() -> None:
    points = [
        *[_Point(index=index, chapter_id="loop") for index in range(8)],
        *[_Point(index=index, chapter_id="decoy") for index in range(8, 12)],
    ]
    expected_indexes = [6, 7, 0, 1, 2, 3]
    rows = [
        [1.0 if index == expected else 0.1 for index in range(len(points))]
        for expected in expected_indexes
    ]

    candidate = best_cyclic_wrap_candidate(
        points=points,
        chapter_bounds=(0, 7),
        previous_index=7,
        similarity_rows=rows,
        edge_fraction=0.5,
        minimum_backtrack_points=3,
        minimum_cyclic_advantage=0.05,
    )

    assert candidate is not None
    assert candidate.index == 3
    assert candidate.score == 1.0
    assert candidate.linear_baseline_score == 0.4
    assert candidate.span_length == 6


def test_cyclic_candidate_is_not_available_before_trailing_edge() -> None:
    points = [_Point(index=index, chapter_id="loop") for index in range(8)]
    rows = [[1.0 for _ in points] for _ in range(6)]

    candidate = best_cyclic_wrap_candidate(
        points=points,
        chapter_bounds=(0, 7),
        previous_index=3,
        similarity_rows=rows,
        edge_fraction=0.35,
        minimum_backtrack_points=3,
        minimum_cyclic_advantage=0.05,
    )

    assert candidate is None


def test_cyclic_evidence_can_reject_next_chapter_decoy_and_confirm_wrap() -> None:
    points = [
        *[
            ReferencePoint(
                index=index,
                chapter_id="loop",
                chapter_title="Loop",
                chapter_start_ms=0.0,
                chapter_end_ms=60_000.0,
                reference_time_ms=index * 10_000.0,
                match_role="instruction",
                guidance_points=(),
                features={"signal": index / 10.0},
            )
            for index in range(6)
        ],
        *[
            ReferencePoint(
                index=index,
                chapter_id="next",
                chapter_title="Next",
                chapter_start_ms=60_000.0,
                chapter_end_ms=100_000.0,
                reference_time_ms=index * 10_000.0,
                match_role="instruction",
                guidance_points=(),
                features={"signal": 0.8},
            )
            for index in range(6, 10)
        ],
        ReferencePoint(
            index=10,
            chapter_id="global-decoy",
            chapter_title="Global decoy",
            chapter_start_ms=100_000.0,
            chapter_end_ms=110_000.0,
            reference_time_ms=100_000.0,
            match_role="instruction",
            guidance_points=(),
            features={"signal": 0.9},
        ),
    ]

    def similarity(reference, learner, _scales) -> float:
        return max(0.0, 1.0 - abs(reference["signal"] - learner["signal"]) * 10)

    localizer = ReferenceSequenceLocalizer(points, {"signal": 0.1}, similarity)
    localizer.previous_index = 5
    history = [points[index].features for index in (2, 3, 4, 5, 0, 1)]

    def score(endpoint: int, selected_history: list[dict[str, float]]) -> float:
        if len(selected_history) == 3:
            return {6: 0.80, 10: 0.95}.get(endpoint, 0.20)
        return {5: 0.30, 6: 0.85}.get(endpoint, 0.20)

    localizer._sequence_score = score  # type: ignore[method-assign]

    first, _, first_diagnostics = localizer.select(history)
    second, score, second_diagnostics = localizer.select(history)

    assert first.index == 5
    assert first_diagnostics["selection_mode"] == "same_chapter_wrap_pending"
    assert first_diagnostics["ordered_transition_evidence_conflicted"] is True
    assert first_diagnostics["cyclic_wrap_candidate_window_index"] == 1
    assert second.index == 1
    assert score == 1.0
    assert second_diagnostics["selection_mode"] == "confirmed_same_chapter_wrap"
