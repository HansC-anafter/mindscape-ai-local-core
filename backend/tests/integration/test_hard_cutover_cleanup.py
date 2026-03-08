"""
Phase 5 — Hard Cutover Cleanup verification tests.

Enforces that all legacy routing paths, shims, and feature-flag branches
have been removed from the codebase.
"""

import os
import subprocess
import pytest

# Repo root
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP_DIR = os.path.join(ROOT, "backend", "app")
TESTS_DIR = os.path.join(ROOT, "backend", "tests")


def _rg_count(pattern: str, *search_dirs: str) -> int:
    """Run ripgrep and return total match count (0 if not found)."""
    try:
        result = subprocess.run(
            ["rg", "-c", pattern] + list(search_dirs),
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if result.returncode != 0:
            return 0
        total = 0
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                total += int(line.rsplit(":", 1)[-1])
        return total
    except FileNotFoundError:
        pytest.skip("ripgrep (rg) not installed")


class TestDeletedFiles:
    """Legacy files must not exist."""

    def test_legacy_message_router_deleted(self):
        path = os.path.join(
            APP_DIR, "services", "conversation", "legacy_message_router.py"
        )
        assert not os.path.exists(path), f"Dead file still exists: {path}"

    def test_pipeline_core_shim_deleted(self):
        path = os.path.join(
            APP_DIR, "services", "conversation", "pipeline_core_shim.py"
        )
        assert not os.path.exists(path), f"Dead file still exists: {path}"

    def test_workspace_bak_deleted(self):
        path = os.path.join(APP_DIR, "models", "workspace.py.bak")
        assert not os.path.exists(path), f"Dead file still exists: {path}"


class TestNoLegacyReferences:
    """Static grep: no runtime references to deleted/deprecated symbols."""

    def test_no_legacy_message_router_refs(self):
        hits = _rg_count(
            r"legacy_message_router|LegacyMessageRouter", APP_DIR, TESTS_DIR
        )
        assert hits == 0, f"Found {hits} references to legacy_message_router"

    def test_no_pipeline_core_shim_refs(self):
        hits = _rg_count(
            r"pipeline_core_shim|route_via_pipeline_core", APP_DIR, TESTS_DIR
        )
        assert hits == 0, f"Found {hits} references to pipeline_core_shim"

    def test_no_should_use_pipeline_core(self):
        hits = _rg_count(r"should_use_pipeline_core", APP_DIR, TESTS_DIR)
        assert hits == 0, f"Found {hits} references to should_use_pipeline_core"

    def test_no_shadow_mode_compat_flags(self):
        hits = _rg_count(
            r"is_shadow_mode|is_compat_post_response_playbook",
            APP_DIR,
            TESTS_DIR,
        )
        assert hits == 0, f"Found {hits} references to shadow/compat flags"

    def test_no_dispatch_task_ir_calls(self):
        hits = _rg_count(r"dispatch_task_ir\(", APP_DIR, TESTS_DIR)
        assert hits == 0, f"Found {hits} calls to dispatch_task_ir"

    def test_no_direct_launch_in_meeting(self):
        meeting_dir = os.path.join(APP_DIR, "services", "orchestration", "meeting")
        hits = _rg_count(r"execution_launcher\.launch\(", meeting_dir)
        assert hits == 0, f"Found {hits} direct launch calls in meeting engine"

    def test_no_workspace_bak_or_fallback_enabled(self):
        hits = _rg_count(
            r"workspace\.py\.bak|agent_fallback_enabled", APP_DIR, TESTS_DIR
        )
        assert (
            hits == 0
        ), f"Found {hits} references to workspace.py.bak/agent_fallback_enabled"


class TestRouteDecisionIsSoleContract:
    """RouteDecision must exist as the sole ingress routing contract."""

    def test_route_decision_exists(self):
        path = os.path.join(APP_DIR, "models", "route_decision.py")
        assert os.path.exists(path), "RouteDecision model missing"

    def test_ingress_router_exists(self):
        path = os.path.join(APP_DIR, "services", "conversation", "ingress_router.py")
        assert os.path.exists(path), "IngressRouter missing"
