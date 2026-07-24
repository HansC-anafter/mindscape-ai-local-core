from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cv2

from rtmp_motion_publisher.pose import PoseDetector, pose_sample_from_result
from rtmp_motion_publisher.windows import MotionWindowAccumulator

from .chapter_clip_source import ChapterClip
from .coverage import assert_chapter_sample_coverage
from .sequential_capture import SequentialFfmpegFrameCapture


ProgressCallback = Callable[[dict[str, Any]], None]


def analyze_chapter_clips(
    clips: list[ChapterClip],
    *,
    profile_id: str,
    model_asset_path: str,
    ffmpeg_bin: str,
    sample_fps: float,
    window_sec: float,
    frame_width: int,
    frame_height: int,
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    detector = PoseDetector.create(model_asset_path)
    windows: list[dict[str, Any]] = []
    try:
        for clip in clips:
            capture = SequentialFfmpegFrameCapture(
                clip.path,
                ffmpeg_bin=ffmpeg_bin,
                sample_fps=sample_fps,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            if not capture.is_opened():
                raise RuntimeError(f"reference_chapter_clip_open_failed:{clip.chapter_id}")
            accumulator = MotionWindowAccumulator(
                live_session_id=profile_id,
                source_session_id=f"reference:{profile_id}:{clip.chapter_id}",
                window_ms=max(250.0, window_sec * 1000.0),
                max_samples=max(1, round(sample_fps * window_sec)),
            )
            frame_index = 0
            chapter_windows: list[dict[str, Any]] = []
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        break
                    timestamp_ms = clip.start_ms + frame_index * 1000.0 / max(
                        0.1,
                        sample_fps,
                    )
                    if timestamp_ms >= clip.end_ms:
                        break
                    result = detector.process(
                        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                        timestamp_ms,
                    )
                    window = accumulator.push(
                        pose_sample_from_result(result, timestamp_ms)
                    )
                    if window is not None:
                        chapter_windows.append(window)
                    frame_index += 1
                final_window = accumulator.flush(clip.end_ms)
                if final_window is not None:
                    chapter_windows.append(final_window)
            finally:
                capture.release()
            sample_coverage = assert_chapter_sample_coverage(
                clip,
                frame_count=frame_index,
                sample_fps=sample_fps,
            )
            if not chapter_windows:
                raise ValueError(
                    f"reference_chapter_feature_windows_missing:{clip.chapter_id}"
                )
            windows.extend(chapter_windows)
            if progress is not None:
                progress(
                    {
                        "event": "reference_chapter_features_complete",
                        "chapter_id": clip.chapter_id,
                        "chapter_index": clip.chapter_index,
                        "frame_count": frame_index,
                        "window_count": len(chapter_windows),
                        "sample_coverage": round(sample_coverage, 4),
                    }
                )
    finally:
        detector.close()
    return windows


__all__ = [
    "analyze_chapter_clips",
]
