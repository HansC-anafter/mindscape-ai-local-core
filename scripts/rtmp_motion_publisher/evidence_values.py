from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class CapturedWindowFrame:
    motion_window_ref: str
    start_ms: float
    end_ms: float
    capture_ms: float
    path: Path


def record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def records(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value] if isinstance(value, list) else []


def number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return fallback


def first_number(
    value: Mapping[str, Any],
    *keys: str,
    fallback: float = 0.0,
) -> float:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            return float(candidate)
    return fallback


def safe_path_part(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "-"
        for character in str(value).strip()
    ).strip("-")
    return cleaned or "unknown"


def is_live_capture_source(value: str) -> bool:
    source = str(value or "").strip().lower()
    return source.startswith(
        ("rtmp://", "rtmps://", "rtsp://", "rtsps://", "avfoundation:")
    )


def segment_frame_coverage_reason(
    segments: list[dict[str, Any]],
    *,
    selected_count: int | None = None,
) -> str | None:
    if not segments:
        return "no_adaptive_segments"
    segment_ids: set[str] = set()
    previous_end_ms: float | None = None
    for segment in segments:
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            return "adaptive_segment_id_missing"
        if segment_id in segment_ids:
            return "adaptive_segment_id_duplicate"
        segment_ids.add(segment_id)
        raw_start_ms = segment.get("segment_start_ms")
        if not isinstance(raw_start_ms, (int, float)) or isinstance(raw_start_ms, bool):
            raw_start_ms = segment.get("start_ms")
        raw_end_ms = segment.get("segment_end_ms")
        if not isinstance(raw_end_ms, (int, float)) or isinstance(raw_end_ms, bool):
            raw_end_ms = segment.get("end_ms")
        if (
            not isinstance(raw_start_ms, (int, float))
            or isinstance(raw_start_ms, bool)
            or not isinstance(raw_end_ms, (int, float))
            or isinstance(raw_end_ms, bool)
            or float(raw_end_ms) <= float(raw_start_ms)
        ):
            return "adaptive_segment_time_range_invalid"
        start_ms = float(raw_start_ms)
        end_ms = float(raw_end_ms)
        if previous_end_ms is not None and start_ms < previous_end_ms:
            return "adaptive_segment_time_range_overlap"
        previous_end_ms = end_ms
    if selected_count is not None and selected_count != len(segments):
        return f"learner_visual_evidence_segment_frame_missing:{len(segments) - selected_count}"
    return None
