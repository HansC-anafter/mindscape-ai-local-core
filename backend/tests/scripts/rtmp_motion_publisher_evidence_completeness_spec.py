from argparse import Namespace
from pathlib import Path
import sys
import types

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
sys.modules.setdefault(
    "cv2",
    types.SimpleNamespace(IMWRITE_JPEG_QUALITY=1, INTER_AREA=2),
)

from rtmp_motion_publisher.evidence import (  # noqa: E402
    CapturedWindowFrame,
    LearnerVisualEvidenceRecorder,
)
from rtmp_motion_publisher.evidence_values import (  # noqa: E402
    segment_frame_coverage_reason,
)
from rtmp_motion_publisher.localized_reference_evidence import (  # noqa: E402
    LocalizedReferenceVisualEvidenceRecorder,
    reference_frame_specs,
)
from rtmp_motion_publisher import localized_reference_evidence  # noqa: E402


def _recorder(tmp_path: Path) -> LearnerVisualEvidenceRecorder:
    return LearnerVisualEvidenceRecorder(
        Namespace(
            rtmp_url="rtsps://media.test/live/learner",
            workspace_id="workspace-1",
            source_session_id="device-session-1",
            disable_learner_visual_evidence=False,
            learner_evidence_max_windows=10,
            learner_evidence_jpeg_quality=78,
            learner_evidence_output_dir=str(tmp_path),
            learner_evidence_storage_dir="/app/evidence",
        ),
        "live-session-1",
    )


def test_missing_segment_frame_never_falls_back_to_another_chapter(
    tmp_path: Path,
) -> None:
    recorder = _recorder(tmp_path)
    recorder.frames = [
        CapturedWindowFrame(
            motion_window_ref="window-1",
            start_ms=0,
            end_ms=2000,
            capture_ms=1000,
            path=tmp_path / "window-1.jpg",
        )
    ]

    result = recorder.finalize(
        {
            "summary": {
                "metadata": {
                    "reference_segments": [
                        {
                            "segment_id": "segment-1",
                            "segment_start_ms": 0,
                            "segment_end_ms": 2000,
                        },
                        {
                            "segment_id": "segment-2",
                            "segment_start_ms": 3000,
                            "segment_end_ms": 4000,
                        },
                    ]
                }
            }
        }
    )

    assert result == {
        "status": "unavailable",
        "reason": "learner_visual_evidence_segment_frame_missing:1",
        "assets": [],
    }


def test_missing_adaptive_segment_id_fails_before_artifact_registration(
    tmp_path: Path,
) -> None:
    recorder = _recorder(tmp_path)

    result = recorder.finalize(
        {
            "summary": {
                "metadata": {
                    "reference_segments": [
                        {"segment_start_ms": 0, "segment_end_ms": 2000}
                    ]
                }
            }
        }
    )

    assert result == {
        "status": "unavailable",
        "reason": "adaptive_segment_id_missing",
        "assets": [],
    }


def test_duplicate_or_overlapping_adaptive_segments_fail_closed() -> None:
    assert segment_frame_coverage_reason([
        {"segment_id": "segment-1", "segment_start_ms": 0, "segment_end_ms": 2000},
        {"segment_id": "segment-1", "segment_start_ms": 2000, "segment_end_ms": 4000},
    ]) == "adaptive_segment_id_duplicate"
    assert segment_frame_coverage_reason([
        {"segment_id": "segment-1", "segment_start_ms": 0, "segment_end_ms": 2500},
        {"segment_id": "segment-2", "segment_start_ms": 2000, "segment_end_ms": 4000},
    ]) == "adaptive_segment_time_range_overlap"
    assert segment_frame_coverage_reason([
        {"segment_id": "segment-1", "segment_start_ms": 2000, "segment_end_ms": 2000},
    ]) == "adaptive_segment_time_range_invalid"


def test_one_motion_window_frame_cannot_fill_two_chapters(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path)
    recorder.frames = [
        CapturedWindowFrame(
            motion_window_ref="boundary-window",
            start_ms=1000,
            end_ms=3000,
            capture_ms=2000,
            path=tmp_path / "boundary-window.jpg",
        )
    ]

    result = recorder.finalize(
        {
            "summary": {
                "metadata": {
                    "reference_segments": [
                        {
                            "segment_id": "segment-1",
                            "segment_start_ms": 0,
                            "segment_end_ms": 2000,
                        },
                        {
                            "segment_id": "segment-2",
                            "segment_start_ms": 2000,
                            "segment_end_ms": 4000,
                        },
                    ]
                }
            }
        }
    )

    assert result == {
        "status": "unavailable",
        "reason": "learner_visual_evidence_segment_frame_missing:1",
        "assets": [],
    }


def test_partial_localized_reference_specs_never_report_ready(tmp_path: Path) -> None:
    segments = [
        {"segment_id": "segment-1", "segment_start_ms": 0, "segment_end_ms": 2000},
        {"segment_id": "segment-2", "segment_start_ms": 2000, "segment_end_ms": 4000},
    ]
    frames = [
        CapturedWindowFrame("window-1", 0, 2000, 1000, tmp_path / "window-1.jpg"),
        CapturedWindowFrame("window-2", 2000, 4000, 3000, tmp_path / "window-2.jpg"),
    ]

    class LearnerRecorder:
        @staticmethod
        def segments(_rollup):
            return segments

        @staticmethod
        def representative_frames(_segments):
            return list(zip(segments, frames, strict=True))

        @staticmethod
        def reference_alignment(motion_window_ref: str):
            return {
                "localization_ready": motion_window_ref == "window-1",
                "reference_profile_id": "profile-1",
                "chapter_id": "chapter-1",
                "reference_time_ms": 1000,
            }

    recorder = object.__new__(LocalizedReferenceVisualEvidenceRecorder)
    recorder.learner_recorder = LearnerRecorder()
    profile = {
        "reference_profile_id": "profile-1",
        "source_ref": "https://reference.test/video",
        "chapters": [
            {"chapter_id": "chapter-1", "ts_start_ms": 0, "ts_end_ms": 4000}
        ],
        "visual_evidence": [
            {
                "chapter_id": "chapter-1",
                "role": "reference",
                "source_kind": "reference_asset",
                "media_kind": "video_clip",
                "artifact_id": "reference-clip-1",
                "mime_type": "video/mp4",
            }
        ],
    }

    result = recorder.finalize({"summary": {}}, profile)

    assert result == {
        "status": "unavailable",
        "reason": "localized_reference_segment_spec_missing:1",
        "assets": [],
    }


def test_explicit_reference_candidate_completes_localized_specs(tmp_path: Path) -> None:
    segment = {
        "segment_id": "segment-1",
        "segment_start_ms": 0,
        "segment_end_ms": 2000,
    }
    frame = CapturedWindowFrame(
        "window-1",
        0,
        2000,
        1000,
        tmp_path / "window-1.jpg",
    )
    profile = {
        "reference_profile_id": "profile-1",
        "source_ref": "https://reference.test/video",
        "chapters": [
            {"chapter_id": "chapter-1", "ts_start_ms": 0, "ts_end_ms": 4000}
        ],
        "visual_evidence": [
            {
                "chapter_id": "chapter-1",
                "role": "reference",
                "source_kind": "reference_asset",
                "media_kind": "video_clip",
                "artifact_id": "reference-clip-1",
                "mime_type": "video/mp4",
            }
        ],
    }

    specs = reference_frame_specs(
        profile,
        [(segment, frame)],
        lambda _window_ref: {
            "visual_evidence_reference_status": "candidate",
            "localization_ready": False,
            "localization_score": 0.73,
            "reference_profile_id": "profile-1",
            "chapter_id": "chapter-1",
            "reference_time_ms": 1250,
        },
    )

    assert len(specs) == 1
    assert specs[0].reference_alignment_status == "candidate"
    assert specs[0].reference_alignment_confidence == 0.73


def test_terminal_reference_capture_uses_last_decodable_frame(monkeypatch) -> None:
    class Capture:
        def __init__(self) -> None:
            self.position: tuple[int, float] | None = None
            self.set_calls: list[tuple[int, float]] = []

        def set(self, prop: int, value: float) -> bool:
            self.position = (prop, value)
            self.set_calls.append((prop, value))
            return True

        def get(self, prop: int) -> float:
            if prop == 2:
                return 290.0
            if prop == 3:
                return 24.0
            return 0.0

        def read(self):
            if self.position == (4, 289):
                return True, np.zeros((2, 3, 3), dtype=np.uint8)
            return False, None

        def release(self) -> None:
            return None

    capture = Capture()
    monkeypatch.setattr(
        localized_reference_evidence,
        "cv2",
        types.SimpleNamespace(
            VideoCapture=lambda _path: capture,
            CAP_PROP_POS_MSEC=1,
            CAP_PROP_FRAME_COUNT=2,
            CAP_PROP_FPS=3,
            CAP_PROP_POS_FRAMES=4,
        ),
    )

    frame = LocalizedReferenceVisualEvidenceRecorder._decode_frame(
        Path("chapter-01.mp4"),
        12_066.0,
    )

    assert frame.shape == (2, 3, 3)
    assert capture.set_calls == [(1, 12_066.0), (4, 289)]


def test_nonterminal_reference_decode_failure_remains_fail_closed(monkeypatch) -> None:
    class Capture:
        def __init__(self) -> None:
            self.set_calls: list[tuple[int, float]] = []

        def set(self, prop: int, value: float) -> bool:
            self.set_calls.append((prop, value))
            return True

        def get(self, prop: int) -> float:
            if prop == 2:
                return 290.0
            if prop == 3:
                return 24.0
            return 0.0

        @staticmethod
        def read():
            return False, None

        def release(self) -> None:
            return None

    capture = Capture()
    monkeypatch.setattr(
        localized_reference_evidence,
        "cv2",
        types.SimpleNamespace(
            VideoCapture=lambda _path: capture,
            CAP_PROP_POS_MSEC=1,
            CAP_PROP_FRAME_COUNT=2,
            CAP_PROP_FPS=3,
            CAP_PROP_POS_FRAMES=4,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="^localized_reference_frame_decode_failed$",
    ):
        LocalizedReferenceVisualEvidenceRecorder._decode_frame(
            Path("chapter-01.mp4"),
            11_000.0,
        )

    assert capture.set_calls == [(1, 11_000.0)]
