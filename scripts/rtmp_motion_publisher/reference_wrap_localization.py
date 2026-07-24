from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Protocol


class IndexedReferencePoint(Protocol):
    index: int
    chapter_id: str


@dataclass(frozen=True)
class CyclicWrapCandidate:
    index: int
    score: float
    linear_baseline_score: float
    span_length: int


def _sampled_cyclic_indexes(
    *,
    first_index: int,
    chapter_size: int,
    endpoint_index: int,
    span_length: int,
    observation_count: int,
) -> list[int]:
    endpoint_offset = endpoint_index - first_index
    offsets = [
        (endpoint_offset - span_length + 1 + step) % chapter_size
        for step in range(span_length)
    ]
    if observation_count == 1 or span_length == 1:
        sampled_offsets = [offsets[0]] * observation_count
    else:
        sampled_offsets = [
            offsets[round(index * (span_length - 1) / (observation_count - 1))]
            for index in range(observation_count)
        ]
    return [first_index + offset for offset in sampled_offsets]


def best_cyclic_wrap_candidate(
    *,
    points: list[IndexedReferencePoint],
    chapter_bounds: tuple[int, int],
    previous_index: int,
    similarity_rows: list[list[float]],
    edge_fraction: float,
    minimum_backtrack_points: int,
    minimum_cyclic_advantage: float,
) -> CyclicWrapCandidate | None:
    """Score a chapter-tail to chapter-head sequence without fixed timing."""

    if not similarity_rows:
        return None
    first_index, last_index = chapter_bounds
    span = last_index - first_index
    if span < minimum_backtrack_points:
        return None
    trailing_edge = first_index + math.ceil(span * (1.0 - edge_fraction))
    if previous_index < trailing_edge:
        return None

    chapter_size = span + 1
    leading_edge = first_index + math.floor(span * edge_fraction)
    observation_count = len(similarity_rows)
    best: CyclicWrapCandidate | None = None
    for endpoint_index in range(first_index, leading_edge + 1):
        minimum_wrapped_span = endpoint_index - first_index + 2
        maximum_span = min(chapter_size, observation_count * 2)
        if minimum_wrapped_span > maximum_span:
            continue
        span_lengths = {
            max(
                minimum_wrapped_span,
                min(maximum_span, max(1, observation_count // 2)),
            ),
            max(minimum_wrapped_span, min(maximum_span, observation_count)),
            maximum_span,
        }
        for span_length in span_lengths:
            sampled_indexes = _sampled_cyclic_indexes(
                first_index=first_index,
                chapter_size=chapter_size,
                endpoint_index=endpoint_index,
                span_length=span_length,
                observation_count=observation_count,
            )
            score = mean(
                row[point_index]
                for row, point_index in zip(similarity_rows, sampled_indexes)
            )
            linear_maximum_span = endpoint_index - first_index + 1
            linear_span_lengths = {
                min(linear_maximum_span, max(1, observation_count // 2)),
                min(linear_maximum_span, observation_count),
                linear_maximum_span,
            }
            linear_baseline_score = max(
                mean(
                    row[point_index]
                    for row, point_index in zip(
                        similarity_rows,
                        _sampled_cyclic_indexes(
                            first_index=first_index,
                            chapter_size=chapter_size,
                            endpoint_index=endpoint_index,
                            span_length=linear_span_length,
                            observation_count=observation_count,
                        ),
                    )
                )
                for linear_span_length in linear_span_lengths
            )
            if score < linear_baseline_score + minimum_cyclic_advantage:
                continue
            candidate = CyclicWrapCandidate(
                index=endpoint_index,
                score=score,
                linear_baseline_score=linear_baseline_score,
                span_length=span_length,
            )
            if best is None or (candidate.score, -candidate.index) > (
                best.score,
                -best.index,
            ):
                best = candidate
    return best


__all__ = ["CyclicWrapCandidate", "best_cyclic_wrap_candidate"]
