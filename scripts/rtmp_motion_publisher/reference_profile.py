from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


MAX_CHAPTERS = 128
MAX_FEATURE_SERIES = 128
MAX_EVIDENCE_REFS = 32
INDEPENDENT_REFERENCE_PROVENANCE = {
    "course_reference_analysis",
    "human_expert_library",
    "independent_reference_asset",
}


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def load_course_chapters(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        chapters = _records(payload)
    else:
        metadata = _record(_record(payload).get("metadata"))
        chapters = _records(metadata.get("course_chapters"))
    if not chapters:
        raise ValueError("course_chapters_not_found")
    return chapters[:MAX_CHAPTERS]


def load_motion_reference_profile(path: str | Path) -> dict[str, Any]:
    profile_path = Path(path).expanduser()
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    profile = _record(payload)
    if profile.get("schema_version") != "motion_reference_profile.v1":
        raise ValueError("motion_reference_profile_schema_invalid")
    if not _text(profile.get("reference_profile_id")):
        raise ValueError("motion_reference_profile_id_missing")
    provenance = _text(_record(profile.get("metadata")).get("comparison_provenance"))
    if provenance not in INDEPENDENT_REFERENCE_PROVENANCE:
        raise ValueError("motion_reference_profile_provenance_not_independent")
    chapters = _records(profile.get("chapters"))
    if not chapters or not all(_records(chapter.get("feature_series")) for chapter in chapters):
        raise ValueError("motion_reference_profile_features_missing")
    return profile


def compact_window_features(window: Mapping[str, Any]) -> dict[str, float]:
    metadata = _record(window.get("metadata"))
    confidence = _record(window.get("confidence_stats"))
    scores = _record(window.get("scores"))
    features = {
        "pose_confidence": _number(
            scores.get("pose_confidence") or confidence.get("mean_confidence")
        ),
        "body_visibility": _number(
            scores.get("body_visibility") or confidence.get("mean_visible_ratio")
        ),
    }
    for key, value in _record(metadata.get("compact_motion_metrics")).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            features[f"posture_{key}"] = _number(value)
    families = (
        ("dwpose_node_deltas", "node_id"),
        ("sway_metrics", "axis"),
        ("phase_metrics", "phase"),
    )
    for family, identifier in families:
        for item in _records(metadata.get(family))[:16]:
            key = _text(item.get(identifier) or item.get("metric"))
            if key:
                features[key] = _number(
                    item.get("delta_score")
                    if item.get("delta_score") is not None
                    else item.get("value")
                )
    return {key: round(value, 4) for key, value in features.items()}


def _window_range(window: Mapping[str, Any]) -> tuple[float, float]:
    start_ms = _number(window.get("ts_start_ms") or window.get("start_ms"))
    end_ms = max(
        start_ms,
        _number(window.get("ts_end_ms") or window.get("end_ms"), start_ms),
    )
    return start_ms, end_ms


def _overlaps(window: Mapping[str, Any], chapter: Mapping[str, Any]) -> bool:
    window_start, window_end = _window_range(window)
    chapter_start = _number(chapter.get("start_ms"))
    chapter_end = max(chapter_start, _number(chapter.get("end_ms"), chapter_start))
    return window_start < chapter_end and window_end > chapter_start


def _downsample(values: list[dict[str, float]], limit: int) -> list[dict[str, float]]:
    if len(values) <= limit:
        return values
    step = len(values) / limit
    return [values[min(len(values) - 1, int(index * step))] for index in range(limit)]


def _mean_confidence(windows: Iterable[Mapping[str, Any]]) -> float:
    values = [
        _number(_record(window.get("confidence_stats")).get("mean_confidence"))
        for window in windows
    ]
    values = [value for value in values if value > 0]
    return round(sum(values) / len(values), 4) if values else 0.0


def build_motion_reference_profile(
    *,
    profile_id: str,
    source_ref: str,
    chapters: list[Mapping[str, Any]],
    windows: list[Mapping[str, Any]],
    visual_evidence: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    profile_chapters: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters[:MAX_CHAPTERS]):
        matched = [window for window in windows if _overlaps(window, chapter)]
        features = _downsample(
            [compact_window_features(window) for window in matched],
            MAX_FEATURE_SERIES,
        )
        evidence_refs = [
            _text(window.get("window_id") or window.get("motion_window_ref"))
            for window in matched
        ]
        evidence_refs = list(dict.fromkeys(ref for ref in evidence_refs if ref))[
            :MAX_EVIDENCE_REFS
        ]
        scoreable = chapter.get("scoreable") is not False
        profile_chapters.append(
            {
                "chapter_id": _text(
                    chapter.get("chapter_id"),
                    f"chapter_{index + 1:03d}",
                ),
                "title": _text(chapter.get("title")) or None,
                "ts_start_ms": max(0.0, _number(chapter.get("start_ms"))),
                "ts_end_ms": max(
                    _number(chapter.get("start_ms")),
                    _number(chapter.get("end_ms")),
                ),
                "match_role": _text(
                    chapter.get("match_role"),
                    "instruction" if scoreable else "context",
                ),
                "feature_series": features,
                "key_posture_anchors": (
                    [features[0], features[len(features) // 2], features[-1]]
                    if len(features) >= 3
                    else features
                ),
                "guidance_points": [
                    _text(item)
                    for item in list(chapter.get("guidance_points") or [])[:8]
                    if _text(item)
                ],
                "confidence": _mean_confidence(matched),
                "evidence_refs": evidence_refs,
                "metadata": {
                    "chapter_index": int(_number(chapter.get("chapter_index"), index)),
                    "source": "independent_local_media_analysis",
                    "window_count": len(matched),
                },
            }
        )
    return {
        "schema_version": "motion_reference_profile.v1",
        "reference_profile_id": profile_id,
        "source_ref": source_ref,
        "reference_source_kind": "course_video",
        "reference_rights_status": "unknown",
        "skeleton_family": "mediapipe_pose_33",
        "chapters": profile_chapters,
        "visual_evidence": [dict(item) for item in (visual_evidence or [])],
        "redaction_notes": [
            "Only compact chapter motion features and bounded evidence refs are retained."
        ],
        "metadata": {
            "comparison_provenance": "independent_reference_asset",
            "source": "local_core.reference_motion_profile_builder",
            "window_count": len(windows),
        },
    }


__all__ = [
    "build_motion_reference_profile",
    "compact_window_features",
    "load_course_chapters",
    "load_motion_reference_profile",
]
