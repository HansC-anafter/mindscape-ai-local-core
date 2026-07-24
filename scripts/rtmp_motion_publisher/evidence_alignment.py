from __future__ import annotations

from typing import Any, Mapping

from .evidence_values import CapturedWindowFrame, number


VISUAL_REFERENCE_STATUS_KEY = "visual_evidence_reference_status"


def visual_reference_alignment(value: Mapping[str, Any]) -> dict[str, Any]:
    alignment = dict(value)
    chapter_id = str(alignment.get("chapter_id") or "").strip()
    reference_time_ms = alignment.get("reference_time_ms")
    if not chapter_id or not isinstance(reference_time_ms, (int, float)):
        return alignment
    alignment[VISUAL_REFERENCE_STATUS_KEY] = (
        "confirmed" if alignment.get("localization_ready") is True else "candidate"
    )
    return alignment


def select_reference_evidence_frame(
    frames: list[CapturedWindowFrame],
    alignments: Mapping[str, Mapping[str, Any]],
) -> CapturedWindowFrame | None:
    aligned = [
        (frame, dict(alignments.get(frame.motion_window_ref) or {}))
        for frame in frames
    ]
    eligible = [
        (frame, alignment)
        for frame, alignment in aligned
        if alignment.get(VISUAL_REFERENCE_STATUS_KEY) in {"confirmed", "candidate"}
        and str(alignment.get("chapter_id") or "").strip()
        and isinstance(alignment.get("reference_time_ms"), (int, float))
    ]
    if not eligible:
        return None
    confirmed = [
        item
        for item in eligible
        if item[1].get(VISUAL_REFERENCE_STATUS_KEY) == "confirmed"
    ]
    pool = confirmed or eligible
    chapter_counts: dict[str, int] = {}
    chapter_scores: dict[str, float] = {}
    for _frame, alignment in pool:
        chapter_id = str(alignment["chapter_id"])
        chapter_counts[chapter_id] = chapter_counts.get(chapter_id, 0) + 1
        chapter_scores[chapter_id] = max(
            chapter_scores.get(chapter_id, 0.0),
            number(alignment.get("localization_score")),
        )
    chapter_id = sorted(
        chapter_counts,
        key=lambda value: (-chapter_counts[value], -chapter_scores[value], value),
    )[0]
    chapter_frames = [
        (frame, alignment)
        for frame, alignment in pool
        if str(alignment["chapter_id"]) == chapter_id
    ]
    chapter_start_ms = min(
        number(alignment.get("chapter_ts_start_ms"))
        for _frame, alignment in chapter_frames
    )
    chapter_end_ms = max(
        number(alignment.get("chapter_ts_end_ms"), chapter_start_ms)
        for _frame, alignment in chapter_frames
    )
    reference_midpoint_ms = (chapter_start_ms + chapter_end_ms) / 2.0
    return min(
        chapter_frames,
        key=lambda item: (
            abs(number(item[1].get("reference_time_ms")) - reference_midpoint_ms),
            -number(item[1].get("localization_score")),
            item[0].capture_ms,
        ),
    )[0]


__all__ = [
    "VISUAL_REFERENCE_STATUS_KEY",
    "select_reference_evidence_frame",
    "visual_reference_alignment",
]
