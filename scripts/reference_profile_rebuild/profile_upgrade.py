from __future__ import annotations

from typing import Any, Mapping

from rtmp_motion_publisher.reference_profile import (
    build_motion_reference_profile,
    compact_window_features,
)


def course_chapters_from_profile(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    chapters = profile.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("reference_profile_chapters_missing")
    result: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, Mapping):
            continue
        start_ms = float(chapter.get("ts_start_ms") or 0.0)
        end_ms = max(start_ms, float(chapter.get("ts_end_ms") or start_ms))
        result.append(
            {
                "chapter_id": str(chapter.get("chapter_id") or "").strip(),
                "chapter_index": index,
                "title": chapter.get("title"),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "scoreable": chapter.get("match_role") not in {"context", "guard"},
                "match_role": chapter.get("match_role") or "instruction",
                "guidance_points": list(chapter.get("guidance_points") or []),
            }
        )
    if not result or any(not item["chapter_id"] for item in result):
        raise ValueError("reference_profile_chapter_id_missing")
    return result


def build_upgraded_profile(
    source_profile: Mapping[str, Any],
    *,
    profile_id: str,
    windows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    source_profile_id = str(source_profile.get("reference_profile_id") or "").strip()
    profile = build_motion_reference_profile(
        profile_id=profile_id,
        source_ref=str(source_profile.get("source_ref") or "").strip(),
        chapters=course_chapters_from_profile(source_profile),
        windows=windows,
        visual_evidence=[
            dict(item)
            for item in list(source_profile.get("visual_evidence") or [])
            if isinstance(item, Mapping)
        ],
    )
    missing = [
        chapter["chapter_id"]
        for chapter in profile["chapters"]
        if not chapter.get("feature_series")
    ]
    if missing:
        raise ValueError("rebuilt_reference_chapter_features_missing:" + ",".join(missing))
    posture_chapter_count = sum(
        any(
            any(str(key).startswith("posture_") for key in feature)
            for feature in chapter["feature_series"]
        )
        for chapter in profile["chapters"]
    )
    if posture_chapter_count == 0:
        raise ValueError("rebuilt_reference_posture_features_missing")
    profile["metadata"].update(
        {
            "feature_schema_version": "motion_reference_posture_geometry.v2",
            "source_reference_profile_id": source_profile_id,
            "chapter_coverage_count": len(profile["chapters"]),
            "posture_feature_chapter_count": posture_chapter_count,
            "visual_evidence_asset_count": len(profile["visual_evidence"]),
        }
    )
    profile["metadata"]["posture_feature_keys"] = sorted(
        {
            key
            for window in windows
            for key in compact_window_features(window)
            if key.startswith("posture_")
        }
    )
    return profile


__all__ = ["build_upgraded_profile", "course_chapters_from_profile"]
