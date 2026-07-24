from __future__ import annotations

import hashlib
import json
import math
import shutil
import threading
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from .api_client import api_post
from .evidence_values import (
    CapturedWindowFrame,
    first_number as _first_number,
    is_live_capture_source as _is_live_capture_source,
    number as _number,
    record as _record,
    records as _records,
    safe_path_part as _safe_path_part,
    segment_frame_coverage_reason as _coverage_reason,
)
from .events import emit
from .evidence_alignment import (
    select_reference_evidence_frame,
    visual_reference_alignment,
)
from .retained_video import (
    RegisteredRetainedVideo,
    RetainedVideoProbe,
    probe_retained_video,
    register_retained_video,
)
from .source_uri import capture_input_kind, public_input_uri


CONTACT_SHEET_COLUMNS = 6
CONTACT_SHEET_FRAME_WIDTH = 320
CONTACT_SHEET_FRAME_HEIGHT = 180


class LearnerVisualEvidenceRecorder:
    """Persist one bounded learner frame per completed motion window."""

    def __init__(self, args: Any, live_session_id: str) -> None:
        self.args = args
        self.live_session_id = live_session_id
        self.enabled = (
            not bool(getattr(args, "disable_learner_visual_evidence", False))
            and _is_live_capture_source(args.rtmp_url)
        )
        self.max_windows = max(1, int(getattr(args, "learner_evidence_max_windows", 1200)))
        self.jpeg_quality = min(
            95,
            max(45, int(getattr(args, "learner_evidence_jpeg_quality", 78))),
        )
        workspace_part = _safe_path_part(args.workspace_id)
        session_part = _safe_path_part(live_session_id)
        default_host_root = (
            Path(__file__).resolve().parents[2]
            / "backend"
            / "data"
            / "workspaces"
            / workspace_part
            / "artifacts"
            / "yogacoach"
            / "live-capture"
            / session_part
        )
        output_dir = str(getattr(args, "learner_evidence_output_dir", "") or "").strip()
        self.host_root = Path(output_dir).expanduser() if output_dir else default_host_root
        storage_dir = str(getattr(args, "learner_evidence_storage_dir", "") or "").strip()
        self.storage_root = Path(storage_dir) if storage_dir else Path(
            "/app/backend/data/workspaces"
        ) / workspace_part / "artifacts" / "yogacoach" / "live-capture" / session_part
        self.window_dir = self.host_root / "motion-window-frames"
        self.frames: list[CapturedWindowFrame] = []
        self.reference_alignments: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.dropped_frames = 0
        if self.enabled:
            self.window_dir.mkdir(parents=True, exist_ok=True)
        else:
            emit(
                {
                    "event": "learner_visual_evidence_disabled",
                    "reason": (
                        "disabled_by_operator"
                        if bool(getattr(args, "disable_learner_visual_evidence", False))
                        else "input_is_not_live_capture"
                    ),
                    "input_uri": public_input_uri(args.rtmp_url),
                }
            )

    def capture_window(self, frame: Any, summary: Mapping[str, Any]) -> None:
        if not self.enabled or frame is None:
            return
        if len(self.frames) >= self.max_windows:
            self.dropped_frames += 1
            return
        motion_window_ref = str(
            summary.get("window_id") or summary.get("motion_window_ref") or ""
        ).strip()
        if not motion_window_ref:
            emit(
                {
                    "event": "learner_visual_evidence_frame_skipped",
                    "reason": "missing_motion_window_ref",
                }
            )
            return
        start_ms = _first_number(summary, "ts_start_ms", "start_ms")
        end_ms = max(
            start_ms,
            _first_number(summary, "ts_end_ms", "end_ms", fallback=start_ms),
        )
        capture_ms = (start_ms + end_ms) / 2.0
        index = len(self.frames)
        path = self.window_dir / f"window-{index:04d}.jpg"
        written = cv2.imwrite(
            str(path),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not written:
            emit(
                {
                    "event": "learner_visual_evidence_frame_write_failed",
                    "motion_window_ref": str(summary.get("motion_window_ref") or ""),
                }
            )
            return
        self.frames.append(
            CapturedWindowFrame(
                motion_window_ref=motion_window_ref,
                start_ms=start_ms,
                end_ms=end_ms,
                capture_ms=capture_ms,
                path=path,
            )
        )

    def record_reference_alignment(self, summary: Mapping[str, Any]) -> None:
        motion_window_ref = str(
            summary.get("window_id") or summary.get("motion_window_ref") or ""
        ).strip()
        metadata = _record(summary.get("metadata"))
        alignment = visual_reference_alignment(
            _record(metadata.get("reference_alignment"))
        )
        if not motion_window_ref or not alignment:
            return
        with self.lock:
            self.reference_alignments[motion_window_ref] = alignment

    def _reference_aligned_frame(
        self,
        frames: list[CapturedWindowFrame],
    ) -> CapturedWindowFrame | None:
        with self.lock:
            alignments = dict(self.reference_alignments)
        return select_reference_evidence_frame(
            frames,
            alignments,
        )

    def segments(self, rollup_response: Mapping[str, Any]) -> list[dict[str, Any]]:
        summary = _record(rollup_response.get("summary"))
        metadata = _record(summary.get("metadata"))
        return _records(metadata.get("reference_segments"))

    def representative_frames(
        self,
        segments: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], CapturedWindowFrame]]:
        selected: list[tuple[dict[str, Any], CapturedWindowFrame]] = []
        used_motion_window_refs: set[str] = set()
        for segment in segments:
            start_ms = _number(segment.get("segment_start_ms") or segment.get("start_ms"))
            end_ms = max(
                start_ms,
                _number(segment.get("segment_end_ms") or segment.get("end_ms"), start_ms),
            )
            midpoint = (start_ms + end_ms) / 2.0
            in_segment = [
                frame
                for frame in self.frames
                if frame.capture_ms >= start_ms and frame.capture_ms <= end_ms
                and frame.motion_window_ref not in used_motion_window_refs
            ]
            if not in_segment:
                continue
            captured = self._reference_aligned_frame(in_segment) or min(
                in_segment,
                key=lambda frame: abs(frame.capture_ms - midpoint),
            )
            used_motion_window_refs.add(captured.motion_window_ref)
            selected.append(
                (
                    segment,
                    captured,
                )
            )
        return selected

    def reference_alignment(self, motion_window_ref: str) -> dict[str, Any]:
        with self.lock:
            return dict(self.reference_alignments.get(motion_window_ref) or {})

    def _write_contact_sheet(
        self,
        selected: list[tuple[dict[str, Any], CapturedWindowFrame]],
    ) -> Path:
        columns = min(CONTACT_SHEET_COLUMNS, max(1, len(selected)))
        rows = max(1, math.ceil(len(selected) / columns))
        cells: list[Any] = []
        for _, captured in selected:
            image = cv2.imread(str(captured.path))
            if image is None:
                raise RuntimeError(f"captured learner frame is unreadable: {captured.path}")
            cells.append(
                cv2.resize(
                    image,
                    (CONTACT_SHEET_FRAME_WIDTH, CONTACT_SHEET_FRAME_HEIGHT),
                    interpolation=cv2.INTER_AREA,
                )
            )
        blank = np.zeros(
            (CONTACT_SHEET_FRAME_HEIGHT, CONTACT_SHEET_FRAME_WIDTH, 3),
            dtype=np.uint8,
        )
        while len(cells) < rows * columns:
            cells.append(blank.copy())
        sheet = np.vstack(
            [np.hstack(cells[row * columns : (row + 1) * columns]) for row in range(rows)]
        )
        path = self.host_root / "learner-adaptive-chapter-contact-sheet.jpg"
        if not cv2.imwrite(
            str(path),
            sheet,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        ):
            raise RuntimeError("learner contact sheet write failed")
        return path

    def _register_contact_sheet(
        self,
        path: Path,
        selected: list[tuple[dict[str, Any], CapturedWindowFrame]],
    ) -> str:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        input_kind = capture_input_kind(
            getattr(self.args, "source_kind", ""),
            getattr(self.args, "transport_kind", ""),
        )
        response = api_post(
            self.args.api_base,
            "/api/v1/artifacts",
            {
                "workspace_id": self.args.workspace_id,
                "type": "illustration",
                "title": f"YogaCoach learner capture evidence: {self.live_session_id}",
                "description": "Adaptive chapter representative frames sampled from the learner capture input.",
                "file_path": str(self.storage_root / path.name),
                "metadata": {
                    "kind": "yogacoach_learner_capture_contact_sheet",
                    "playbook_code": "yogacoach_practice_diary",
                    "role": "learner",
                    "source_kind": "learner_capture",
                    "capture_session_id": self.args.source_session_id,
                    "media_session_id": getattr(self.args, "media_session_id", "") or None,
                    "live_session_id": self.live_session_id,
                    "meeting_session_id": self.args.meeting_id,
                    "receiver_identity": getattr(self.args, "receiver_identity", "") or None,
                    "transport_kind": getattr(self.args, "transport_kind", "") or None,
                    "capture_input_kind": input_kind,
                    "capture_input_uri": public_input_uri(self.args.rtmp_url),
                    "lineage": "learner_capture_motion_window_frame",
                    "mime_type": "image/jpeg",
                    "sha256": checksum,
                    "captured_window_frame_count": len(self.frames),
                    "adaptive_segment_frame_count": len(selected),
                    "dropped_frame_count": self.dropped_frames,
                    "selected_motion_window_refs": [
                        captured.motion_window_ref for _, captured in selected
                    ],
                    "sprite_grid_columns": min(CONTACT_SHEET_COLUMNS, len(selected)),
                    "sprite_grid_rows": math.ceil(len(selected) / CONTACT_SHEET_COLUMNS),
                },
            },
            timeout_sec=self.args.api_timeout_sec,
            retry_count=self.args.api_retry_count,
            retry_backoff_sec=self.args.api_retry_backoff_sec,
        )
        artifact_id = str(response.get("id") or "").strip()
        if not artifact_id:
            raise RuntimeError("learner contact sheet artifact registration returned no id")
        return artifact_id

    def _probe_retained_video(self, path: Path) -> RetainedVideoProbe:
        return probe_retained_video(
            path,
            ffmpeg_bin=str(getattr(self.args, "ffmpeg_bin", "ffmpeg")),
            timeout_sec=float(getattr(self.args, "closeout_api_timeout_sec", 30.0)),
        )

    def _register_retained_video(
        self,
        segments: list[dict[str, Any]],
    ) -> RegisteredRetainedVideo:
        input_kind = capture_input_kind(
            getattr(self.args, "source_kind", ""),
            getattr(self.args, "transport_kind", ""),
        )
        return register_retained_video(
            args=self.args,
            host_root=self.host_root,
            storage_root=self.storage_root,
            live_session_id=self.live_session_id,
            segments=segments,
            input_kind=input_kind,
            input_uri=public_input_uri(self.args.rtmp_url),
            probe=self._probe_retained_video,
            register_artifact=api_post,
        )

    def finalize(self, rollup_response: Mapping[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "unavailable", "reason": "input_is_not_live_capture", "assets": []}
        segments = self.segments(rollup_response)
        completeness_reason = _coverage_reason(segments)
        if completeness_reason:
            return {"status": "unavailable", "reason": completeness_reason, "assets": []}
        selected = self.representative_frames(segments)
        completeness_reason = _coverage_reason(segments, selected_count=len(selected))
        if completeness_reason:
            return {"status": "unavailable", "reason": completeness_reason, "assets": []}
        try:
            contact_sheet_path = self._write_contact_sheet(selected)
            artifact_id = self._register_contact_sheet(contact_sheet_path, selected)
            retained_video = self._register_retained_video(segments)
            columns = min(CONTACT_SHEET_COLUMNS, len(selected))
            rows = math.ceil(len(selected) / columns)
            source_ref = f"mindscape://device_binding/session/{self.args.source_session_id}"
            input_kind = capture_input_kind(
                getattr(self.args, "source_kind", ""),
                getattr(self.args, "transport_kind", ""),
            )
            assets = []
            for index, (segment, captured) in enumerate(selected):
                start_ms = _number(segment.get("segment_start_ms") or segment.get("start_ms"))
                end_ms = max(
                    start_ms,
                    _number(segment.get("segment_end_ms") or segment.get("end_ms"), start_ms),
                )
                chapter_id = str(segment.get("segment_id") or "").strip()
                if not chapter_id:
                    continue
                assets.append(
                    {
                        "asset_id": f"{chapter_id}:learner:capture-snapshot",
                        "chapter_id": chapter_id,
                        "role": "learner",
                        "media_kind": "snapshot",
                        "artifact_id": artifact_id,
                        "mime_type": "image/jpeg",
                        "label": "Learner capture representative frame",
                        "time_range_ms": [start_ms, end_ms],
                        "capture_ms": captured.capture_ms,
                        "sprite_frame_index": index,
                        "sprite_grid_columns": columns,
                        "sprite_grid_rows": rows,
                        "source_ref": source_ref,
                        "lineage": "learner_capture_motion_window_frame",
                        "source_kind": "learner_capture",
                        "capture_session_id": self.args.source_session_id,
                        "media_session_id": getattr(self.args, "media_session_id", "") or None,
                        "receiver_identity": getattr(self.args, "receiver_identity", "") or None,
                        "transport_kind": getattr(self.args, "transport_kind", "") or None,
                        "capture_input_kind": input_kind,
                        "motion_window_ref": captured.motion_window_ref,
                    }
                )
                assets.append(
                    {
                        "asset_id": f"{chapter_id}:learner:capture-video-clip",
                        "chapter_id": chapter_id,
                        "role": "learner",
                        "media_kind": "video_clip",
                        "artifact_id": retained_video.artifact_id,
                        "mime_type": "video/mp4",
                        "label": "Learner capture chapter clip",
                        "time_range_ms": [start_ms, end_ms],
                        "media_time_range_ms": [
                            min(start_ms, retained_video.duration_ms),
                            min(end_ms, retained_video.duration_ms),
                        ],
                        "media_duration_ms": round(retained_video.duration_ms, 3),
                        "capture_ms": captured.capture_ms,
                        "source_ref": source_ref,
                        "lineage": "learner_capture_retained_by_analysis_reader",
                        "source_kind": "learner_capture",
                        "capture_session_id": self.args.source_session_id,
                        "media_session_id": getattr(self.args, "media_session_id", "") or None,
                        "receiver_identity": getattr(self.args, "receiver_identity", "") or None,
                        "transport_kind": getattr(self.args, "transport_kind", "") or None,
                        "capture_input_kind": input_kind,
                        "motion_window_ref": captured.motion_window_ref,
                    }
                )
            manifest = {
                "schema_version": "yogacoach.learner_visual_evidence.v1",
                "status": "ready",
                "artifact_id": artifact_id,
                "clip_artifact_id": retained_video.artifact_id,
                "clip_duration_ms": round(retained_video.duration_ms, 3),
                "capture_session_id": self.args.source_session_id,
                "media_session_id": getattr(self.args, "media_session_id", "") or None,
                "live_session_id": self.live_session_id,
                "receiver_identity": getattr(self.args, "receiver_identity", "") or None,
                "transport_kind": getattr(self.args, "transport_kind", "") or None,
                "capture_input_kind": input_kind,
                "captured_window_frame_count": len(self.frames),
                "adaptive_segment_frame_count": len(selected),
                "adaptive_segment_clip_count": len(selected),
                "assets": assets,
            }
            manifest_path = self.host_root / "learner-visual-evidence-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            emit(
                {
                    "event": "learner_visual_evidence_ready",
                    "artifact_id": artifact_id,
                    "clip_artifact_id": retained_video.artifact_id,
                    "captured_window_frame_count": len(self.frames),
                    "adaptive_segment_frame_count": len(selected),
                    "adaptive_segment_clip_count": len(selected),
                }
            )
            return manifest
        except Exception as exc:
            emit({"event": "learner_visual_evidence_failed", "error": str(exc)})
            return {"status": "unavailable", "reason": str(exc), "assets": []}

    def cleanup_transient_frames(self) -> None:
        """Remove per-window frames only after the durable closeout succeeds."""
        if not self.enabled or not self.window_dir.exists():
            return
        try:
            shutil.rmtree(self.window_dir)
        except OSError as exc:
            emit(
                {
                    "event": "learner_visual_evidence_transient_cleanup_failed",
                    "captured_window_frame_count": len(self.frames),
                    "error": str(exc),
                }
            )
            return
        emit(
            {
                "event": "learner_visual_evidence_transient_frames_cleaned",
                "captured_window_frame_count": len(self.frames),
            }
        )


__all__ = ["LearnerVisualEvidenceRecorder"]
