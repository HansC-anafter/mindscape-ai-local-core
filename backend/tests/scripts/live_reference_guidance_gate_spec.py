from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.reference_guidance_gate import (  # noqa: E402
    CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS,
    ReferenceGuidanceGate,
)


def test_guidance_gate_rejects_a_single_window_chapter_relock() -> None:
    gate = ReferenceGuidanceGate()
    initial = gate.observe("chapter-one", localization_ready=True)
    assert initial.ready is True
    assert initial.committed_chapter_id == "chapter-one"

    false_relock = gate.observe("chapter-two", localization_ready=True)
    assert false_relock.ready is False
    assert false_relock.pending_chapter_id == "chapter-two"
    assert false_relock.pending_count == 1

    reacquiring = gate.observe("chapter-two", localization_ready=False)
    assert reacquiring.ready is False
    assert reacquiring.pending_chapter_id is None
    recovered = gate.observe("chapter-one", localization_ready=True)
    assert recovered.ready is True
    assert recovered.committed_chapter_id == "chapter-one"


def test_guidance_gate_promotes_a_stable_chapter_change() -> None:
    gate = ReferenceGuidanceGate()
    gate.observe("chapter-one", localization_ready=True)

    for expected_count in range(1, CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS):
        state = gate.observe("chapter-two", localization_ready=True)
        assert state.ready is False
        assert state.pending_count == expected_count

    promoted = gate.observe("chapter-two", localization_ready=True)

    assert promoted.ready is True
    assert promoted.committed_chapter_id == "chapter-two"
    assert promoted.pending_chapter_id is None
    assert promoted.pending_count == 0
