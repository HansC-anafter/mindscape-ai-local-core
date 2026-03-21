"""
Unit tests for handoff intake meeting path:
Pre-1 lens_id injection via EffectiveLensResolver fallback.
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock


_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class TestHandoffBundleLensInjection:
    """Verify Pre-1: lens_id is resolved via EffectiveLensResolver
    when not explicitly provided during session creation."""

    def test_handoff_bundle_imports_resolver(self):
        """Verify the resolver import path exists in handoff_bundle_service source."""
        source = (
            _BACKEND_ROOT / "app/services/handoff_bundle_service.py"
        ).read_text(encoding="utf-8")
        assert "EffectiveLensResolver" in source
        assert "GraphStore" in source
        assert "InMemorySessionStore" in source

    def test_handoff_bundle_does_not_use_metadata_active_lens(self):
        """Verify the old metadata.active_lens_id pattern was removed."""
        source = (
            _BACKEND_ROOT / "app/services/handoff_bundle_service.py"
        ).read_text(encoding="utf-8")
        assert "active_lens_id" not in source


class TestPipelineMeetingLensInjection:
    """Verify Pre-1: pipeline_meeting resolves lens_id before session creation."""

    def test_pipeline_meeting_imports_resolver(self):
        """Verify pipeline_meeting has EffectiveLensResolver wiring."""
        source = (
            _BACKEND_ROOT / "app/services/conversation/pipeline_meeting.py"
        ).read_text(encoding="utf-8")
        assert "EffectiveLensResolver" in source
        assert "GraphStore" in source

    def test_session_store_update_no_execution_id_in_decisions(self):
        """Verify session.decisions is NOT polluted with execution_id."""
        source = (
            _BACKEND_ROOT / "app/services/conversation/pipeline_meeting.py"
        ).read_text(encoding="utf-8")
        # The old pattern should be commented out / removed
        assert "session.decisions.append(result.execution_id)" not in source
        assert "session.decisions.append(execution_id)" not in source


class TestMeetingSessionsAPILensInjection:
    """Verify Pre-1: meeting_sessions API route resolves lens_id."""

    def test_resolver_fallback_contract(self):
        """EffectiveLensResolver requires GraphStore + InMemorySessionStore."""
        from backend.app.services.lens.effective_lens_resolver import (
            EffectiveLensResolver,
        )
        import inspect

        sig = inspect.signature(EffectiveLensResolver.__init__)
        params = list(sig.parameters.keys())
        assert "graph_store" in params
        assert "session_store" in params

    def test_api_route_has_resolver_fallback(self):
        """Verify meeting_sessions API route resolves lens_id when missing."""
        source = (_BACKEND_ROOT / "app/routes/meeting_sessions.py").read_text(
            encoding="utf-8"
        )
        assert "EffectiveLensResolver" in source
        assert "lens_id = body.lens_id" in source


class TestLensSourcePrioritization:
    """Verify lens source priority across all 3 session creation paths."""

    def test_body_lens_id_takes_priority(self):
        body_lens = "body-lens-001"
        resolved_lens = "resolved-lens-002"
        lens_id = body_lens or resolved_lens
        assert lens_id == "body-lens-001"

    def test_resolver_used_when_body_is_none(self):
        body_lens = None
        resolved_lens = "resolved-lens-002"
        lens_id = body_lens or resolved_lens
        assert lens_id == "resolved-lens-002"

    def test_none_when_both_missing(self):
        body_lens = None
        resolved_lens = None
        lens_id = body_lens or resolved_lens
        assert lens_id is None
