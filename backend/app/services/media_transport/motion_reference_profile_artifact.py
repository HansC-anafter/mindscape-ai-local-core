"""Resolve one workspace-owned motion reference profile for a live receiver."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit


MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT = "motion_reference_profile_artifact.v1"
MOTION_REFERENCE_PROFILE_SCHEMA = "motion_reference_profile.v1"
MAX_PROFILE_BYTES = 8 * 1024 * 1024
MAX_PROFILE_CHAPTERS = 128
MAX_CHAPTER_FEATURES = 128
MAX_REFERENCE_VISUAL_EVIDENCE = 256
INDEPENDENT_REFERENCE_PROVENANCE = frozenset(
    {
        "course_reference_analysis",
        "human_expert_library",
        "independent_reference_asset",
    }
)
BILIBILI_VIDEO_HOSTS = frozenset(
    {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}
)
BILIBILI_VIDEO_PATH = re.compile(r"^/video/(?P<bvid>BV[0-9A-Za-z]+)/?$")


class MotionReferenceProfileArtifactError(RuntimeError):
    """Stable validation failure for a selected reference profile artifact."""

    def __init__(self, reason: str, *, status_code: int = 422) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class ArtifactReader(Protocol):
    def get_artifact(self, artifact_id: str) -> Any: ...


class ArtifactLookup(ArtifactReader, Protocol):
    def find_by_source_ref(
        self,
        *,
        workspace_id: str,
        source_ref: str,
        limit: int = 2,
    ) -> list[Any]: ...


@dataclass(frozen=True)
class ResolvedMotionReferenceProfile:
    artifact_id: str
    storage_ref: str
    reference_profile_id: str
    source_ref: str | None
    chapter_count: int

    def receiver_ref(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "storage_ref": self.storage_ref,
            "reference_profile_id": self.reference_profile_id,
        }


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _required_text(value: Any, reason: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MotionReferenceProfileArtifactError(reason)
    return text


def canonical_motion_reference_source_ref(value: Any) -> str:
    """Collapse provider tracking URLs into one stable media identity."""

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text
    hostname = str(parsed.hostname or "").lower()
    path_match = BILIBILI_VIDEO_PATH.fullmatch(parsed.path)
    if parsed.scheme in {"http", "https"} and hostname in BILIBILI_VIDEO_HOSTS and path_match:
        return f"https://www.bilibili.com/video/{path_match.group('bvid')}/"
    return text


def _data_root() -> Path:
    return Path(os.getenv("LOCAL_CORE_DATA_DIR", "/app/data")).resolve()


def _resolve_storage_path(workspace_id: str, storage_ref: Any) -> Path:
    raw_path = _required_text(
        storage_ref,
        "motion_reference_profile_storage_ref_missing",
    )
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_storage_ref_not_absolute"
        )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_file_not_found",
            status_code=404,
        ) from exc
    allowed_root = (
        _data_root()
        / "workspaces"
        / workspace_id
        / "artifacts"
        / "yogacoach"
        / "reference-profiles"
    ).resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_storage_ref_outside_workspace"
        ) from exc
    if not resolved.is_file():
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_file_not_found",
            status_code=404,
        )
    size = resolved.stat().st_size
    if size <= 0 or size > MAX_PROFILE_BYTES:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_file_size_invalid"
        )
    return resolved


def _validate_reference_visual_evidence(
    profile: Mapping[str, Any],
    *,
    chapters: list[dict[str, Any]],
    source_ref: str,
) -> None:
    assets = _records(profile.get("visual_evidence"))
    if not assets or len(assets) > MAX_REFERENCE_VISUAL_EVIDENCE:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_visual_evidence_count_invalid"
        )
    chapter_ids = {
        _required_text(
            chapter.get("chapter_id"),
            "motion_reference_profile_chapter_id_missing",
        )
        for chapter in chapters
    }
    covered_chapter_ids: set[str] = set()
    asset_ids: set[str] = set()
    forbidden_provenance = {
        "capture_session_id",
        "media_session_id",
        "receiver_identity",
        "transport_kind",
        "capture_input_kind",
        "motion_window_ref",
    }
    for asset in assets:
        asset_id = _required_text(
            asset.get("asset_id"),
            "motion_reference_profile_visual_evidence_asset_id_missing",
        )
        if asset_id in asset_ids:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_visual_evidence_asset_id_duplicate"
            )
        asset_ids.add(asset_id)
        chapter_id = _required_text(
            asset.get("chapter_id"),
            "motion_reference_profile_visual_evidence_chapter_id_missing",
        )
        if chapter_id not in chapter_ids:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_visual_evidence_chapter_unknown"
            )
        if asset.get("role") != "reference" or (
            asset.get("source_kind") != "reference_asset"
        ):
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_visual_evidence_provenance_invalid"
            )
        if any(asset.get(name) not in (None, "") for name in forbidden_provenance):
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_visual_evidence_receiver_provenance_invalid"
            )
        if asset.get("media_kind") not in {"snapshot", "video_clip"}:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_visual_evidence_media_kind_invalid"
            )
        for name, reason in (
            ("artifact_id", "motion_reference_profile_visual_evidence_artifact_id_missing"),
            ("mime_type", "motion_reference_profile_visual_evidence_mime_type_missing"),
            ("label", "motion_reference_profile_visual_evidence_label_missing"),
            ("lineage", "motion_reference_profile_visual_evidence_lineage_missing"),
        ):
            _required_text(asset.get(name), reason)
        asset_source_ref = canonical_motion_reference_source_ref(
            asset.get("source_ref")
        )
        if asset_source_ref != source_ref:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_visual_evidence_source_mismatch"
            )
        covered_chapter_ids.add(chapter_id)
    if covered_chapter_ids != chapter_ids:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_visual_evidence_chapter_coverage_incomplete"
        )


def _validate_profile(path: Path) -> tuple[str, str | None, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_json_invalid"
        ) from exc
    profile = _record(payload)
    if profile.get("schema_version") != MOTION_REFERENCE_PROFILE_SCHEMA:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_schema_invalid"
        )
    profile_id = _required_text(
        profile.get("reference_profile_id"),
        "motion_reference_profile_id_missing",
    )
    provenance = str(
        _record(profile.get("metadata")).get("comparison_provenance") or ""
    ).strip()
    if provenance not in INDEPENDENT_REFERENCE_PROVENANCE:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_provenance_not_independent"
        )
    chapters = _records(profile.get("chapters"))
    if not chapters or len(chapters) > MAX_PROFILE_CHAPTERS:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_chapter_count_invalid"
        )
    for chapter in chapters:
        _required_text(
            chapter.get("chapter_id"),
            "motion_reference_profile_chapter_id_missing",
        )
        features = _records(chapter.get("feature_series"))
        if not features or len(features) > MAX_CHAPTER_FEATURES:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_features_invalid"
            )
    source_ref = canonical_motion_reference_source_ref(profile.get("source_ref")) or None
    if not source_ref:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_source_ref_missing"
        )
    _validate_reference_visual_evidence(
        profile,
        chapters=chapters,
        source_ref=source_ref,
    )
    return profile_id, source_ref, len(chapters)


def resolve_motion_reference_profile_artifact(
    *,
    artifact_store: ArtifactReader,
    workspace_id: str,
    artifact_id: str,
) -> ResolvedMotionReferenceProfile:
    """Resolve and validate a profile without accepting a caller-supplied path."""

    artifact = artifact_store.get_artifact(artifact_id)
    if artifact is None:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_artifact_not_found",
            status_code=404,
        )
    if str(getattr(artifact, "workspace_id", "") or "") != workspace_id:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_workspace_mismatch",
            status_code=403,
        )
    metadata = _record(getattr(artifact, "metadata", None))
    if metadata.get("artifact_contract") != MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_artifact_contract_invalid"
        )
    path = _resolve_storage_path(workspace_id, getattr(artifact, "storage_ref", None))
    profile_id, source_ref, chapter_count = _validate_profile(path)
    declared_profile_id = str(metadata.get("reference_profile_id") or "").strip()
    if declared_profile_id and declared_profile_id != profile_id:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_artifact_identity_mismatch"
        )
    declared_source_ref = canonical_motion_reference_source_ref(metadata.get("source_ref"))
    if not declared_source_ref or declared_source_ref != source_ref:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_artifact_source_mismatch"
        )
    return ResolvedMotionReferenceProfile(
        artifact_id=str(getattr(artifact, "id", artifact_id) or artifact_id),
        storage_ref=str(path),
        reference_profile_id=profile_id,
        source_ref=source_ref,
        chapter_count=chapter_count,
    )


def resolve_selected_motion_reference_profile(
    *,
    artifact_store: ArtifactLookup,
    workspace_id: str,
    artifact_id: str | None,
    source_ref: str | None,
) -> ResolvedMotionReferenceProfile | None:
    selected_artifact_id = str(artifact_id or "").strip()
    selected_source_ref = canonical_motion_reference_source_ref(source_ref)
    if selected_artifact_id:
        resolved = resolve_motion_reference_profile_artifact(
            artifact_store=artifact_store,
            workspace_id=workspace_id,
            artifact_id=selected_artifact_id,
        )
    elif selected_source_ref:
        candidates = artifact_store.find_by_source_ref(
            workspace_id=workspace_id,
            source_ref=selected_source_ref,
            limit=2,
        )
        if not candidates:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_not_materialized"
            )
        if len(candidates) > 1:
            raise MotionReferenceProfileArtifactError(
                "motion_reference_profile_source_conflict",
                status_code=409,
            )
        resolved = resolve_motion_reference_profile_artifact(
            artifact_store=artifact_store,
            workspace_id=workspace_id,
            artifact_id=str(candidates[0].id),
        )
    else:
        return None
    if selected_source_ref and resolved.source_ref != selected_source_ref:
        raise MotionReferenceProfileArtifactError(
            "motion_reference_profile_selection_mismatch"
        )
    return resolved


__all__ = [
    "MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT",
    "MotionReferenceProfileArtifactError",
    "ResolvedMotionReferenceProfile",
    "canonical_motion_reference_source_ref",
    "resolve_motion_reference_profile_artifact",
    "resolve_selected_motion_reference_profile",
]
