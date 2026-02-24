"""
Unit tests for LensPatchService lifecycle:
lens state comparison, delta generation, and patch creation.
"""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.services.orchestration.meeting.lens_patch_service import (
    LensPatchService,
)
from backend.app.models.lens_patch import LensPatch, PatchStatus


@dataclass
class FakeLensNode:
    node_id: str
    node_label: str
    state: object


class FakeState:
    def __init__(self, value):
        self.value = value


@dataclass
class FakeEffectiveLens:
    nodes: List[FakeLensNode] = field(default_factory=list)
    hash: Optional[str] = None
    global_preset_id: str = "preset-default"


class FakeSession:
    def __init__(self, session_id="sess-patch-001", lens_id="lens-001"):
        self.id = session_id
        self.lens_id = lens_id
        self.workspace_id = "ws-001"


class TestLensPatchGeneration:
    def test_no_patch_when_both_none(self):
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=None,
            lens_after=None,
        )
        assert result is None

    def test_no_patch_when_hashes_match(self):
        lens_a = FakeEffectiveLens(hash="same-hash")
        lens_b = FakeEffectiveLens(hash="same-hash")
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=lens_a,
            lens_after=lens_b,
        )
        assert result is None

    def test_patch_generated_on_state_change(self):
        lens_before = FakeEffectiveLens(
            nodes=[
                FakeLensNode("n1", "Creativity", FakeState("keep")),
                FakeLensNode("n2", "Precision", FakeState("keep")),
            ],
            hash="hash-before",
        )
        lens_after = FakeEffectiveLens(
            nodes=[
                FakeLensNode("n1", "Creativity", FakeState("emphasize")),
                FakeLensNode("n2", "Precision", FakeState("keep")),
            ],
            hash="hash-after",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        assert result is not None
        assert isinstance(result, LensPatch)
        assert "n1" in result.delta
        assert result.delta["n1"]["before"] == "keep"
        assert result.delta["n1"]["after"] == "emphasize"
        # n2 unchanged, should not be in delta
        assert "n2" not in result.delta

    def test_patch_detects_added_node(self):
        lens_before = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h1",
        )
        lens_after = FakeEffectiveLens(
            nodes=[
                FakeLensNode("n1", "A", FakeState("keep")),
                FakeLensNode("n2", "B", FakeState("emphasize")),
            ],
            hash="h2",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        assert result is not None
        assert result.delta["n2"]["before"] == "absent"
        assert result.delta["n2"]["after"] == "added"

    def test_patch_detects_removed_node(self):
        lens_before = FakeEffectiveLens(
            nodes=[
                FakeLensNode("n1", "A", FakeState("keep")),
                FakeLensNode("n2", "B", FakeState("emphasize")),
            ],
            hash="h1",
        )
        lens_after = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h2",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        assert result is not None
        assert result.delta["n2"]["before"] == "present"
        assert result.delta["n2"]["after"] == "removed"


class TestLensPatchFields:
    def test_patch_has_correct_session_id(self):
        lens_before = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("off"))],
            hash="h1",
        )
        lens_after = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h2",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(session_id="sess-x"),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        assert result.meeting_session_id == "sess-x"

    def test_patch_has_lens_id_from_session(self):
        lens_before = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h1",
        )
        lens_after = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("emphasize"))],
            hash="h2",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(lens_id="lens-custom"),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        assert result.lens_id == "lens-custom"

    def test_patch_proposed_status(self):
        lens_before = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h1",
        )
        lens_after = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("off"))],
            hash="h2",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        assert result.status == PatchStatus.PROPOSED

    def test_no_delta_means_no_patch(self):
        """When nodes are identical despite different hashes, no patch."""
        lens_before = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h-different-1",
        )
        lens_after = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("keep"))],
            hash="h-different-2",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=lens_before,
            lens_after=lens_after,
        )
        # Hashes differ but nodes are identical - no delta
        assert result is None

    def test_patch_when_lens_before_is_none(self):
        """Session started without a lens, ended with one."""
        lens_after = FakeEffectiveLens(
            nodes=[FakeLensNode("n1", "A", FakeState("emphasize"))],
            hash="h-after",
        )
        svc = LensPatchService()
        result = svc.generate_patch_from_session(
            session=FakeSession(),
            lens_before=None,
            lens_after=lens_after,
        )
        assert result is not None
        assert result.delta["n1"]["before"] == "absent"
        assert result.delta["n1"]["after"] == "added"
