from __future__ import annotations

from .chapter_clip_source import ChapterClip


MIN_CHAPTER_SAMPLE_COVERAGE = 0.95


def assert_chapter_sample_coverage(
    clip: ChapterClip,
    *,
    frame_count: int,
    sample_fps: float,
) -> float:
    expected = max(
        1,
        int((clip.end_ms - clip.start_ms) * max(0.1, sample_fps) / 1000.0),
    )
    coverage = min(1.0, frame_count / expected)
    if coverage < MIN_CHAPTER_SAMPLE_COVERAGE:
        raise ValueError(
            "reference_chapter_sample_coverage_incomplete:"
            f"{clip.chapter_id}:{frame_count}/{expected}:{coverage:.4f}"
        )
    return coverage


__all__ = ["assert_chapter_sample_coverage", "MIN_CHAPTER_SAMPLE_COVERAGE"]

