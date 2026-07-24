from __future__ import annotations

from typing import Any, Mapping


MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT = "motion_reference_profile_artifact.v1"


def artifact_metadata(
    *,
    profile: Mapping[str, Any],
    source_profile: Mapping[str, Any],
    profile_id: str,
    checksum: str,
) -> dict[str, Any]:
    source_ref = str(profile.get("source_ref") or "").strip()
    if not source_ref:
        raise ValueError("rebuilt_reference_profile_source_ref_missing")
    chapters = list(profile.get("chapters") or [])
    visual_evidence = list(profile.get("visual_evidence") or [])
    return {
        "kind": "yogacoach_motion_reference_profile",
        "playbook_code": "yogacoach_reference_profile",
        "artifact_contract": MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
        "reference_profile_id": profile_id,
        "source_reference_profile_id": source_profile["reference_profile_id"],
        "source_ref": source_ref,
        "comparison_provenance": "independent_reference_asset",
        "feature_schema_version": "motion_reference_posture_geometry.v2",
        "chapter_count": len(chapters),
        "motion_window_count": sum(
            len(chapter.get("feature_series") or [])
            for chapter in chapters
            if isinstance(chapter, Mapping)
        ),
        "visual_evidence_asset_count": len(visual_evidence),
        "mime_type": "application/json",
        "sha256": checksum,
    }


__all__ = [
    "MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT",
    "artifact_metadata",
]
