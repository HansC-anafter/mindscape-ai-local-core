from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from .api_client import api_post


CONTACT_SHEET_COLUMNS = 6
CONTACT_SHEET_FRAME_WIDTH = 320
CONTACT_SHEET_FRAME_HEIGHT = 180


def _number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return fallback


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


@dataclass
class ReferenceFrameCandidate:
    chapter_id: str
    chapter_start_ms: float
    chapter_end_ms: float
    midpoint_ms: float
    capture_ms: float | None = None
    distance_ms: float = float("inf")
    frame: Any = None


class ReferenceVisualEvidenceRecorder:
    """Create one durable representative frame for every reference chapter."""

    def __init__(
        self,
        *,
        chapters: Sequence[Mapping[str, Any]],
        profile_id: str,
        source_ref: str,
        workspace_id: str,
        output_dir: str | Path,
        storage_dir: str | Path,
        api_base: str,
        jpeg_quality: int = 78,
        api_timeout_sec: float = 30.0,
    ) -> None:
        self.profile_id = profile_id
        self.source_ref = source_ref
        self.workspace_id = workspace_id
        self.output_dir = Path(output_dir).expanduser()
        self.storage_dir = Path(storage_dir)
        self.api_base = api_base
        self.jpeg_quality = min(95, max(45, int(jpeg_quality)))
        self.api_timeout_sec = max(1.0, float(api_timeout_sec))
        self.candidates = [
            self._candidate(chapter, index)
            for index, chapter in enumerate(chapters)
        ]
        if not self.candidates:
            raise ValueError("reference_visual_evidence_chapters_missing")

    @staticmethod
    def _candidate(
        chapter: Mapping[str, Any],
        index: int,
    ) -> ReferenceFrameCandidate:
        start_ms = max(0.0, _number(chapter.get("start_ms")))
        end_ms = max(start_ms, _number(chapter.get("end_ms"), start_ms))
        if end_ms <= start_ms:
            raise ValueError("reference_visual_evidence_chapter_range_invalid")
        return ReferenceFrameCandidate(
            chapter_id=_text(chapter.get("chapter_id"), f"chapter_{index + 1:03d}"),
            chapter_start_ms=start_ms,
            chapter_end_ms=end_ms,
            midpoint_ms=(start_ms + end_ms) / 2.0,
        )

    def observe(self, frame: Any, timestamp_ms: float) -> None:
        for candidate in self.candidates:
            if not (
                candidate.chapter_start_ms
                <= timestamp_ms
                <= candidate.chapter_end_ms
            ):
                continue
            distance_ms = abs(timestamp_ms - candidate.midpoint_ms)
            if distance_ms >= candidate.distance_ms:
                continue
            candidate.capture_ms = timestamp_ms
            candidate.distance_ms = distance_ms
            candidate.frame = frame.copy()

    def _write_contact_sheet(self) -> tuple[Path, int, int]:
        missing = [item.chapter_id for item in self.candidates if item.frame is None]
        if missing:
            raise ValueError(
                "reference_visual_evidence_chapter_frames_missing:"
                + ",".join(missing)
            )
        columns = min(CONTACT_SHEET_COLUMNS, len(self.candidates))
        rows = math.ceil(len(self.candidates) / columns)
        cells = [
            cv2.resize(
                item.frame,
                (CONTACT_SHEET_FRAME_WIDTH, CONTACT_SHEET_FRAME_HEIGHT),
                interpolation=cv2.INTER_AREA,
            )
            for item in self.candidates
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
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "reference-chapter-contact-sheet.jpg"
        if not cv2.imwrite(
            str(path),
            sheet,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        ):
            raise RuntimeError("reference_visual_evidence_contact_sheet_write_failed")
        return path, columns, rows

    def _register_contact_sheet(
        self,
        path: Path,
        *,
        columns: int,
        rows: int,
    ) -> str:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        result = api_post(
            self.api_base,
            "/api/v1/artifacts",
            {
                "workspace_id": self.workspace_id,
                "type": "illustration",
                "title": f"YogaCoach reference chapter evidence: {self.profile_id}",
                "description": (
                    "Independent reference chapter representative frames used by "
                    "Practice Diary comparisons."
                ),
                "file_path": str(self.storage_dir / path.name),
                "metadata": {
                    "kind": "yogacoach_reference_chapter_contact_sheet",
                    "playbook_code": "yogacoach_reference_profile",
                    "role": "reference",
                    "source_kind": "reference_asset",
                    "source_ref": self.source_ref,
                    "reference_profile_id": self.profile_id,
                    "lineage": "independent_reference_media_chapter_frame",
                    "mime_type": "image/jpeg",
                    "sha256": checksum,
                    "chapter_count": len(self.candidates),
                    "sprite_grid_columns": columns,
                    "sprite_grid_rows": rows,
                },
            },
            timeout_sec=self.api_timeout_sec,
            retry_count=1,
            retry_backoff_sec=0.0,
        )
        artifact_id = _text(result.get("id"))
        if not artifact_id:
            raise RuntimeError(
                "reference_visual_evidence_artifact_registration_returned_no_id"
            )
        return artifact_id

    def finalize(self) -> list[dict[str, Any]]:
        path, columns, rows = self._write_contact_sheet()
        artifact_id = self._register_contact_sheet(
            path,
            columns=columns,
            rows=rows,
        )
        return [
            {
                "asset_id": f"{item.chapter_id}:reference:snapshot",
                "chapter_id": item.chapter_id,
                "role": "reference",
                "media_kind": "snapshot",
                "artifact_id": artifact_id,
                "mime_type": "image/jpeg",
                "label": "Reference chapter representative frame",
                "time_range_ms": [
                    item.chapter_start_ms,
                    item.chapter_end_ms,
                ],
                "media_time_range_ms": [
                    item.chapter_start_ms,
                    item.chapter_end_ms,
                ],
                "capture_ms": item.capture_ms,
                "sprite_frame_index": index,
                "sprite_grid_columns": columns,
                "sprite_grid_rows": rows,
                "source_ref": self.source_ref,
                "lineage": "independent_reference_media_chapter_frame",
                "source_kind": "reference_asset",
            }
            for index, item in enumerate(self.candidates)
        ]


__all__ = ["ReferenceVisualEvidenceRecorder"]
