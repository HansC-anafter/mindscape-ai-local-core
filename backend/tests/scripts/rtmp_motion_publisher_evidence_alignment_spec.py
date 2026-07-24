from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.evidence_alignment import (  # noqa: E402
    VISUAL_REFERENCE_STATUS_KEY,
    select_reference_evidence_frame,
    visual_reference_alignment,
)
from rtmp_motion_publisher.evidence_values import CapturedWindowFrame  # noqa: E402


def _frame(index: int) -> CapturedWindowFrame:
    return CapturedWindowFrame(
        motion_window_ref=f"window-{index}",
        start_ms=float(index * 1000),
        end_ms=float((index + 1) * 1000),
        capture_ms=float(index * 1000 + 500),
        path=Path(f"/tmp/window-{index}.jpg"),
    )


def test_visual_reference_alignment_marks_unconfirmed_match_as_candidate() -> None:
    alignment = visual_reference_alignment(
        {
            "chapter_id": "reference-1",
            "reference_time_ms": 1200.0,
            "localization_ready": False,
        }
    )

    assert alignment[VISUAL_REFERENCE_STATUS_KEY] == "candidate"


def test_confirmed_frame_wins_over_higher_scoring_candidate() -> None:
    frames = [_frame(0), _frame(1)]
    alignments = {
        "window-0": visual_reference_alignment(
            {
                "chapter_id": "reference-confirmed",
                "chapter_ts_start_ms": 0.0,
                "chapter_ts_end_ms": 4000.0,
                "reference_time_ms": 1000.0,
                "localization_score": 0.61,
                "localization_ready": True,
            }
        ),
        "window-1": visual_reference_alignment(
            {
                "chapter_id": "reference-candidate",
                "chapter_ts_start_ms": 0.0,
                "chapter_ts_end_ms": 4000.0,
                "reference_time_ms": 2000.0,
                "localization_score": 0.99,
                "localization_ready": False,
            }
        ),
    }

    selected = select_reference_evidence_frame(frames, alignments)

    assert selected == frames[0]


def test_candidate_frame_is_retained_when_chapter_alignment_is_unconfirmed() -> None:
    frames = [_frame(0), _frame(1), _frame(2)]
    alignments = {
        frame.motion_window_ref: visual_reference_alignment(
            {
                "chapter_id": "reference-candidate",
                "chapter_ts_start_ms": 0.0,
                "chapter_ts_end_ms": 4000.0,
                "reference_time_ms": 1000.0 + index * 1000.0,
                "localization_score": 0.7 + index * 0.05,
                "localization_ready": False,
            }
        )
        for index, frame in enumerate(frames)
    }

    selected = select_reference_evidence_frame(frames, alignments)

    assert selected == frames[1]
