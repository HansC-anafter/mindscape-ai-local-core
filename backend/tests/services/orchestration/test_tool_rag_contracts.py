"""Tests for Tool RAG contract behaviors.

Covers:
- tool_coverage_warnings in session metadata (C3)
- Supervisor dual-source coverage with get_by_id (C5)
- MeetingEngine uploaded_files parameter (C1)
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock
import pytest


_BACKEND_ROOT = Path(__file__).resolve().parents[3]


# ── Contract 1: MeetingEngine uploaded_files attribute ──


class TestMeetingEngineUploadedFiles:
    """C1: MeetingEngine accepts and stores uploaded_files parameter."""

    def test_init_accepts_uploaded_files_param(self):
        """Verify __init__ signature includes uploaded_files parameter."""
        import ast

        tree = ast.parse(
            (
                _BACKEND_ROOT / "app/services/orchestration/meeting/engine.py"
            ).read_text(encoding="utf-8")
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "__init__":
                # Check it's in MeetingEngine class
                param_names = [arg.arg for arg in node.args.args]
                if "session" in param_names and "workspace" in param_names:
                    assert (
                        "uploaded_files" in param_names
                    ), "MeetingEngine.__init__ must accept uploaded_files param"
                    # Check default value is None
                    defaults = node.args.defaults
                    kw_defaults = node.args.kw_defaults
                    all_defaults = defaults + kw_defaults
                    # Find uploaded_files default
                    kw_args = node.args.kwonlyargs
                    for i, kw in enumerate(kw_args):
                        if kw.arg == "uploaded_files":
                            default = kw_defaults[i]
                            assert (
                                isinstance(default, ast.Constant)
                                and default.value is None
                            ), "uploaded_files default must be None"
                            return
                    # Also check regular args with defaults
                    n_defaults = len(defaults)
                    n_args = len(node.args.args)
                    for i, arg in enumerate(node.args.args):
                        if arg.arg == "uploaded_files":
                            default_idx = i - (n_args - n_defaults)
                            if default_idx >= 0:
                                assert isinstance(
                                    defaults[default_idx], ast.Constant
                                ), "uploaded_files default must be None"
                            return
                    return
        pytest.fail("MeetingEngine.__init__ not found")

    def test_uploaded_files_stored_as_list(self):
        """Verify __init__ body assigns self._uploaded_files = list(...)."""
        import ast

        source = (
            _BACKEND_ROOT / "app/services/orchestration/meeting/engine.py"
        ).read_text(encoding="utf-8")

        assert (
            "self._uploaded_files" in source
        ), "engine.py must contain self._uploaded_files assignment"
        assert (
            "list(uploaded_files or [])" in source
        ), "uploaded_files must be normalized with list(uploaded_files or [])"


# ── Contract 5: Supervisor dual-source coverage ──


class TestSupervisorToolCoverage:
    """C5: Supervisor reads session metadata for playbook launches."""

    @pytest.fixture
    def tasks_store(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session = MagicMock(return_value=[])
        return store

    @pytest.fixture
    def session_store(self):
        return MagicMock()

    def test_reads_metadata_before_early_return(self, tasks_store, session_store):
        """When no tasks but playbook launches exist, coverage reflects them."""
        from backend.app.services.orchestration.meeting.meeting_supervisor import (
            MeetingSupervisor,
        )

        session = MagicMock()
        session.metadata = {
            "execution_ids": ["exec-1", "exec-2"],
            "tool_coverage_warnings": [],
        }
        session_store.get_by_id = MagicMock(return_value=session)

        supervisor = MeetingSupervisor(
            tasks_store=tasks_store, session_store=session_store
        )
        result = asyncio.get_event_loop().run_until_complete(
            supervisor.on_session_closed("sess-1")
        )

        assert result["playbook_launches"] == 2
        assert result["total_tasks"] == 0
        session_store.get_by_id.assert_called_once_with("sess-1")

    def test_uses_get_by_id_not_get(self, tasks_store, session_store):
        """Verify supervisor calls get_by_id, not get."""
        from backend.app.services.orchestration.meeting.meeting_supervisor import (
            MeetingSupervisor,
        )

        session = MagicMock()
        session.metadata = {"execution_ids": [], "tool_coverage_warnings": []}
        session_store.get_by_id = MagicMock(return_value=session)
        session_store.get = MagicMock(
            side_effect=AttributeError("Use get_by_id, not get")
        )

        supervisor = MeetingSupervisor(
            tasks_store=tasks_store, session_store=session_store
        )
        asyncio.get_event_loop().run_until_complete(
            supervisor.on_session_closed("sess-1")
        )

        session_store.get_by_id.assert_called_once()
        session_store.get.assert_not_called()

    def test_file_coverage_gaps_from_warnings(self, tasks_store, session_store):
        """Verify file_coverage_gaps counts tool_coverage_warnings."""
        from backend.app.services.orchestration.meeting.meeting_supervisor import (
            MeetingSupervisor,
        )

        session = MagicMock()
        session.metadata = {
            "execution_ids": [],
            "tool_coverage_warnings": [
                "FILE_WITHOUT_TOOL: f1",
                "FILE_WITHOUT_TOOL: f2",
            ],
        }
        session_store.get_by_id = MagicMock(return_value=session)

        supervisor = MeetingSupervisor(
            tasks_store=tasks_store, session_store=session_store
        )
        result = asyncio.get_event_loop().run_until_complete(
            supervisor.on_session_closed("sess-1")
        )

        assert result["file_coverage_gaps"] == 2

    def test_no_session_store_graceful(self, tasks_store):
        """Without session_store, supervisor still works with zero coverage."""
        from backend.app.services.orchestration.meeting.meeting_supervisor import (
            MeetingSupervisor,
        )

        supervisor = MeetingSupervisor(tasks_store=tasks_store, session_store=None)
        result = asyncio.get_event_loop().run_until_complete(
            supervisor.on_session_closed("sess-1")
        )

        assert result["playbook_launches"] == 0
        assert result["file_coverage_gaps"] == 0

    def test_tool_tasks_counted_from_execution_context(
        self, tasks_store, session_store
    ):
        """Tasks with execution_context.tool_name counted as tool_tasks."""
        from backend.app.services.orchestration.meeting.meeting_supervisor import (
            MeetingSupervisor,
        )

        task_with_tool = MagicMock()
        task_with_tool.status = "succeeded"
        task_with_tool.execution_context = {"tool_name": "content_ingest"}
        task_with_tool.updated_at = None

        task_without_tool = MagicMock()
        task_without_tool.status = "succeeded"
        task_without_tool.execution_context = {}
        task_without_tool.updated_at = None

        tasks_store.list_tasks_by_meeting_session.return_value = [
            task_with_tool,
            task_without_tool,
        ]

        session = MagicMock()
        session.metadata = {"execution_ids": [], "tool_coverage_warnings": []}
        session_store.get_by_id = MagicMock(return_value=session)

        supervisor = MeetingSupervisor(
            tasks_store=tasks_store, session_store=session_store
        )
        result = asyncio.get_event_loop().run_until_complete(
            supervisor.on_session_closed("sess-1")
        )

        assert result["tool_tasks"] == 1
        assert result["total_tasks"] == 2


# ── Contract 4: Handoff path uploaded_files=None ──


class TestHandoffUploadedFiles:
    """C4: handoff_bundle_service passes uploaded_files explicitly."""

    def test_handoff_engine_call_includes_uploaded_files(self):
        """Verify MeetingEngine() call in handoff includes uploaded_files kwarg."""
        import ast

        source = (_BACKEND_ROOT / "app/services/handoff_bundle_service.py").read_text(
            encoding="utf-8"
        )

        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "MeetingEngine":
                    kw_names = [kw.arg for kw in node.keywords]
                    if "uploaded_files" in kw_names:
                        found = True
                        break
        assert found, (
            "MeetingEngine() call in handoff_bundle_service.py "
            "must include uploaded_files keyword argument"
        )
