from __future__ import annotations

import hashlib
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote

import cv2
import numpy as np
import requests

from .api_client import api_post
from .evidence import CapturedWindowFrame, LearnerVisualEvidenceRecorder
from .evidence_alignment import VISUAL_REFERENCE_STATUS_KEY
from .events import emit


CONTACT_SHEET_COLUMNS = 6
CONTACT_SHEET_FRAME_WIDTH = 320
CONTACT_SHEET_FRAME_HEIGHT = 180


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return fallback


@dataclass(frozen=True)
class LocalizedReferenceFrameSpec:
    segment_id: str
    segment_start_ms: float
    segment_end_ms: float
    motion_window_ref: str
    reference_chapter_id: str
    reference_capture_ms: float
    chapter_start_ms: float
    chapter_end_ms: float
    clip_artifact_id: str
    clip_mime_type: str
    source_ref: str
    reference_alignment_status: str
    reference_alignment_confidence: float

    @property
    def clip_capture_ms(self) -> float:
        return min(
            max(0.0, self.reference_capture_ms - self.chapter_start_ms),
            max(0.0, self.chapter_end_ms - self.chapter_start_ms),
        )

    @property
    def clip_time_range_ms(self) -> list[float]:
        chapter_duration = max(0.0, self.chapter_end_ms - self.chapter_start_ms)
        segment_duration = max(0.0, self.segment_end_ms - self.segment_start_ms)
        duration = min(chapter_duration, segment_duration)
        start_ms = min(
            max(0.0, self.clip_capture_ms - duration / 2.0),
            max(0.0, chapter_duration - duration),
        )
        return [start_ms, start_ms + duration]


def reference_frame_specs(
    profile: Mapping[str, Any],
    selected: list[tuple[dict[str, Any], CapturedWindowFrame]],
    alignment_for: Callable[[str], Mapping[str, Any]],
) -> list[LocalizedReferenceFrameSpec]:
    profile_id = str(profile.get("reference_profile_id") or "").strip()
    source_ref = str(profile.get("source_ref") or "").strip()
    chapters = {
        str(chapter.get("chapter_id") or "").strip(): chapter
        for chapter in _records(profile.get("chapters"))
        if str(chapter.get("chapter_id") or "").strip()
    }
    clips = {
        str(asset.get("chapter_id") or "").strip(): asset
        for asset in _records(profile.get("visual_evidence"))
        if asset.get("role") == "reference"
        and asset.get("source_kind") == "reference_asset"
        and asset.get("media_kind") == "video_clip"
        and str(asset.get("chapter_id") or "").strip()
    }
    specs: list[LocalizedReferenceFrameSpec] = []
    for segment, learner_frame in selected:
        alignment = _record(alignment_for(learner_frame.motion_window_ref))
        alignment_status = str(
            alignment.get(VISUAL_REFERENCE_STATUS_KEY) or ""
        ).strip()
        if not alignment_status and alignment.get("localization_ready") is True:
            alignment_status = "confirmed"
        if alignment_status not in {"confirmed", "candidate"}:
            continue
        alignment_profile_id = str(
            alignment.get("reference_profile_id") or ""
        ).strip()
        if alignment_profile_id and alignment_profile_id != profile_id:
            continue
        chapter_id = str(alignment.get("chapter_id") or "").strip()
        chapter = chapters.get(chapter_id)
        clip = clips.get(chapter_id)
        segment_id = str(segment.get("segment_id") or "").strip()
        reference_time = alignment.get("reference_time_ms")
        if (
            not chapter
            or not clip
            or not segment_id
            or not isinstance(reference_time, (int, float))
        ):
            continue
        chapter_start_ms = _number(chapter.get("ts_start_ms"))
        chapter_end_ms = max(
            chapter_start_ms,
            _number(chapter.get("ts_end_ms"), chapter_start_ms),
        )
        specs.append(
            LocalizedReferenceFrameSpec(
                segment_id=segment_id,
                segment_start_ms=_number(
                    segment.get("segment_start_ms") or segment.get("start_ms")
                ),
                segment_end_ms=_number(
                    segment.get("segment_end_ms") or segment.get("end_ms")
                ),
                motion_window_ref=learner_frame.motion_window_ref,
                reference_chapter_id=chapter_id,
                reference_capture_ms=min(
                    chapter_end_ms,
                    max(chapter_start_ms, float(reference_time)),
                ),
                chapter_start_ms=chapter_start_ms,
                chapter_end_ms=chapter_end_ms,
                clip_artifact_id=str(clip.get("artifact_id") or "").strip(),
                clip_mime_type=str(clip.get("mime_type") or "video/mp4").strip(),
                source_ref=source_ref,
                reference_alignment_status=alignment_status,
                reference_alignment_confidence=max(
                    0.0,
                    min(
                        1.0,
                        _number(
                            alignment.get("confidence"),
                            _number(alignment.get("localization_score")),
                        ),
                    ),
                ),
            )
        )
    return [item for item in specs if item.clip_artifact_id and item.source_ref]


class LocalizedReferenceVisualEvidenceRecorder:
    """Extract exact reference frames paired to selected learner windows."""

    def __init__(
        self,
        args: Any,
        live_session_id: str,
        learner_recorder: LearnerVisualEvidenceRecorder,
    ) -> None:
        self.args = args
        self.live_session_id = live_session_id
        self.learner_recorder = learner_recorder
        self.host_root = learner_recorder.host_root
        self.storage_root = learner_recorder.storage_root
        self.cache_root = self.host_root / "reference-clip-cache"
        self.jpeg_quality = learner_recorder.jpeg_quality

    def _download_clip(self, artifact_id: str) -> Path:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        path = self.cache_root / f"{artifact_id}.mp4"
        if path.is_file() and path.stat().st_size > 0:
            return path
        url = (
            f"{self.args.api_base.rstrip('/')}/api/v1/workspaces/"
            f"{quote(self.args.workspace_id, safe='')}/artifacts/"
            f"{quote(artifact_id, safe='')}/file"
        )
        response = requests.get(
            url,
            timeout=float(getattr(self.args, "closeout_api_timeout_sec", 30.0)),
        )
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("localized_reference_clip_empty")
        path.write_bytes(response.content)
        return path

    @staticmethod
    def _decode_frame(path: Path, capture_ms: float) -> Any:
        capture = cv2.VideoCapture(str(path))
        try:
            target_ms = max(0.0, capture_ms)
            capture.set(cv2.CAP_PROP_POS_MSEC, target_ms)
            ok, frame = capture.read()
            if ok and frame is not None:
                return frame

            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_rate = float(capture.get(cv2.CAP_PROP_FPS))
            if frame_count > 0 and frame_rate > 0.0:
                frame_interval_ms = 1000.0 / frame_rate
                last_frame_ms = (frame_count - 1) * frame_interval_ms
                if last_frame_ms <= target_ms <= last_frame_ms + frame_interval_ms:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
                    ok, frame = capture.read()
                    if ok and frame is not None:
                        return frame
            raise RuntimeError("localized_reference_frame_decode_failed")
        finally:
            capture.release()

    def _write_contact_sheet(
        self,
        frames: list[Any],
    ) -> tuple[Path, int, int]:
        columns = min(CONTACT_SHEET_COLUMNS, len(frames))
        rows = max(1, math.ceil(len(frames) / columns))
        cells = [
            cv2.resize(
                frame,
                (CONTACT_SHEET_FRAME_WIDTH, CONTACT_SHEET_FRAME_HEIGHT),
                interpolation=cv2.INTER_AREA,
            )
            for frame in frames
        ]
        blank = np.zeros(
            (CONTACT_SHEET_FRAME_HEIGHT, CONTACT_SHEET_FRAME_WIDTH, 3),
            dtype=np.uint8,
        )
        while len(cells) < rows * columns:
            cells.append(blank.copy())
        sheet = np.vstack(
            [
                np.hstack(cells[row * columns : (row + 1) * columns])
                for row in range(rows)
            ]
        )
        path = self.host_root / "reference-localized-contact-sheet.jpg"
        if not cv2.imwrite(
            str(path),
            sheet,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        ):
            raise RuntimeError("localized_reference_contact_sheet_write_failed")
        return path, columns, rows

    def _register_contact_sheet(
        self,
        path: Path,
        specs: list[LocalizedReferenceFrameSpec],
        *,
        columns: int,
        rows: int,
    ) -> str:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        result = api_post(
            self.args.api_base,
            "/api/v1/artifacts",
            {
                "workspace_id": self.args.workspace_id,
                "type": "illustration",
                "title": (
                    f"YogaCoach localized reference evidence: {self.live_session_id}"
                ),
                "description": (
                    "Reference frames extracted from independent chapter clips at "
                    "the exact times selected for learner comparison."
                ),
                "file_path": str(self.storage_root / path.name),
                "metadata": {
                    "kind": "yogacoach_localized_reference_contact_sheet",
                    "playbook_code": "yogacoach_practice_diary",
                    "role": "reference",
                    "source_kind": "reference_asset",
                    "source_ref": specs[0].source_ref,
                    "live_session_id": self.live_session_id,
                    "meeting_session_id": self.args.meeting_id,
                    "lineage": "independent_reference_clip_localized_frame",
                    "mime_type": "image/jpeg",
                    "sha256": checksum,
                    "adaptive_segment_frame_count": len(specs),
                    "sprite_grid_columns": columns,
                    "sprite_grid_rows": rows,
                },
            },
            timeout_sec=float(
                getattr(self.args, "closeout_api_timeout_sec", self.args.api_timeout_sec)
            ),
            retry_count=self.args.api_retry_count,
            retry_backoff_sec=self.args.api_retry_backoff_sec,
        )
        artifact_id = str(result.get("id") or "").strip()
        if not artifact_id:
            raise RuntimeError("localized_reference_artifact_registration_missing")
        return artifact_id

    def finalize(
        self,
        rollup_response: Mapping[str, Any],
        profile: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not profile:
            return {
                "status": "unavailable",
                "reason": "motion_reference_profile_missing",
                "assets": [],
            }
        segments = self.learner_recorder.segments(rollup_response)
        if not segments:
            return {
                "status": "unavailable",
                "reason": "localized_reference_segments_missing",
                "assets": [],
            }
        selected = self.learner_recorder.representative_frames(segments)
        if len(selected) != len(segments):
            return {
                "status": "unavailable",
                "reason": "localized_reference_learner_segment_frame_missing",
                "assets": [],
            }
        specs = reference_frame_specs(
            profile,
            selected,
            self.learner_recorder.reference_alignment,
        )
        spec_segment_ids = {item.segment_id for item in specs}
        if len(specs) != len(segments) or len(spec_segment_ids) != len(segments):
            return {
                "status": "unavailable",
                "reason": (
                    "localized_reference_segment_spec_missing:"
                    f"{len(segments) - len(spec_segment_ids)}"
                ),
                "assets": [],
            }
        try:
            clip_paths = {
                artifact_id: self._download_clip(artifact_id)
                for artifact_id in {item.clip_artifact_id for item in specs}
            }
            frames = [
                self._decode_frame(
                    clip_paths[item.clip_artifact_id],
                    item.clip_capture_ms,
                )
                for item in specs
            ]
            path, columns, rows = self._write_contact_sheet(frames)
            artifact_id = self._register_contact_sheet(
                path,
                specs,
                columns=columns,
                rows=rows,
            )
            assets = []
            for index, item in enumerate(specs):
                assets.append({
                    "asset_id": f"{item.segment_id}:reference:localized-snapshot",
                    "chapter_id": item.segment_id,
                    "role": "reference",
                    "media_kind": "snapshot",
                    "artifact_id": artifact_id,
                    "mime_type": "image/jpeg",
                    "label": (
                        "Localized reference representative frame"
                        if item.reference_alignment_status == "confirmed"
                        else "Candidate reference representative frame"
                    ),
                    "time_range_ms": [
                        item.segment_start_ms,
                        item.segment_end_ms,
                    ],
                    "media_time_range_ms": [
                        item.clip_capture_ms,
                        item.clip_capture_ms,
                    ],
                    "capture_ms": item.reference_capture_ms,
                    "motion_window_ref": item.motion_window_ref,
                    "sprite_frame_index": index,
                    "sprite_grid_columns": columns,
                    "sprite_grid_rows": rows,
                    "source_ref": item.source_ref,
                    "lineage": (
                        "independent_reference_clip_localized_frame"
                        if item.reference_alignment_status == "confirmed"
                        else "independent_reference_clip_candidate_frame"
                    ),
                    "source_kind": "reference_asset",
                    "reference_alignment_status": item.reference_alignment_status,
                    "reference_alignment_confidence": item.reference_alignment_confidence,
                })
                assets.append({
                    "asset_id": f"{item.segment_id}:reference:localized-video-clip",
                    "chapter_id": item.segment_id,
                    "role": "reference",
                    "media_kind": "video_clip",
                    "artifact_id": item.clip_artifact_id,
                    "mime_type": item.clip_mime_type,
                    "label": (
                        "Localized reference chapter clip"
                        if item.reference_alignment_status == "confirmed"
                        else "Candidate reference chapter clip"
                    ),
                    "time_range_ms": [
                        item.segment_start_ms,
                        item.segment_end_ms,
                    ],
                    "media_time_range_ms": item.clip_time_range_ms,
                    "capture_ms": item.reference_capture_ms,
                    "motion_window_ref": item.motion_window_ref,
                    "source_ref": item.source_ref,
                    "lineage": (
                        "independent_reference_clip_localized_segment"
                        if item.reference_alignment_status == "confirmed"
                        else "independent_reference_clip_candidate_segment"
                    ),
                    "source_kind": "reference_asset",
                    "reference_alignment_status": item.reference_alignment_status,
                    "reference_alignment_confidence": item.reference_alignment_confidence,
                })
            emit(
                {
                    "event": "localized_reference_visual_evidence_ready",
                    "artifact_id": artifact_id,
                    "adaptive_segment_frame_count": len(specs),
                    "adaptive_segment_clip_count": len(specs),
                }
            )
            return {
                "schema_version": "yogacoach.reference_visual_evidence.v1",
                "status": "ready",
                "artifact_id": artifact_id,
                "clip_artifact_ids": sorted({item.clip_artifact_id for item in specs}),
                "assets": assets,
            }
        except Exception as exc:
            emit(
                {
                    "event": "localized_reference_visual_evidence_failed",
                    "error": str(exc),
                }
            )
            return {"status": "unavailable", "reason": str(exc), "assets": []}
        finally:
            if self.cache_root.exists():
                shutil.rmtree(self.cache_root, ignore_errors=True)


__all__ = [
    "LocalizedReferenceFrameSpec",
    "LocalizedReferenceVisualEvidenceRecorder",
    "reference_frame_specs",
]
