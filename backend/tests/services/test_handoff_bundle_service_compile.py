"""Fake-only HandoffBundleService compile lifecycle tests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

import pytest

from backend.app.services.handoff_bundle_service import HandoffBundleService

from handoff_bundle_service_test_support import (
    FakeMeetingResult,
    SIGNING_KEY_FIXTURE,
    install_fake_compile_modules,
    make_handoff_bundle,
)


def _workspace():
    workspace = MagicMock()
    workspace.id = "ws_001"
    workspace.resolved_executor_runtime = "codex_cli"
    return workspace


async def _fake_result_run(result):
    async def _fake_run(*args, **kwargs):
        return result

    return _fake_run


class TestCompileHappyPath:
    """Happy-path tests for intake_and_compile with mocked MeetingEngine."""

    @pytest.mark.asyncio
    async def test_compile_happy_path_produces_task_ir(self):
        """Full compile path: bundle -> MeetingEngine -> TaskIR -> persist."""
        from backend.app.models.task_ir import TaskIR, TaskStatus

        fake_ir = TaskIR(
            task_id="task_hp_001",
            workspace_id="ws_001",
            intent_instance_id="intent-test-001",
            actor_id="test-user",
            status=TaskStatus.PENDING,
        )
        fake_result = FakeMeetingResult(
            task_ir=fake_ir,
            action_items=[{"title": "Build"}],
        )
        fake_session = MagicMock()
        fake_session.id = "sess-hp-001"
        fake_session.workspace_id = "ws_001"

        mock_session_store = MagicMock()
        mock_session_store.list_by_workspace.return_value = []
        mock_session_store.get_active_session.return_value = None
        mock_session_store.create.return_value = None

        mock_ms_cls = MagicMock()
        mock_ms_cls.new.return_value = fake_session

        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = await _fake_result_run(fake_result)
        mock_engine_cls.return_value = mock_engine

        mock_ir_store = MagicMock()
        mock_ir_store.replace_task_ir.return_value = True
        mock_compile_job_store = MagicMock()
        mock_compile_job_store.get_latest_for_session.return_value = None

        with install_fake_compile_modules(
            meeting_engine_cls=mock_engine_cls,
            session_store=mock_session_store,
            meeting_session_cls=mock_ms_cls,
            task_ir_store=mock_ir_store,
            compile_job_store=mock_compile_job_store,
        ) as fake_modules:
            result = await HandoffBundleService().intake_and_compile(
                bundle=make_handoff_bundle(),
                workspace=_workspace(),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

        assert result["status"] == "compiled"
        assert result["compile_job_id"]
        assert result["task_ir_id"] == "task_hp_001"
        assert result["persisted"] is True
        assert result["action_items_count"] == 1
        mock_engine_cls.assert_called_once()
        assert mock_engine_cls.call_args.kwargs["executor_runtime"] == "codex_cli"
        assert (
            mock_engine_cls.call_args.kwargs["execution_launcher"]
            is fake_modules.execution_launcher
        )
        fake_modules.build_execution_launcher.assert_called_once()
        mock_session_store.get_active_session.assert_called_once_with(
            "ws_001",
            "p1",
            "t1",
        )
        mock_session_store.create.assert_called_once_with(fake_session)
        mock_ir_store.replace_task_ir.assert_called_once_with(fake_ir)
        mock_compile_job_store.create.assert_called_once()
        mock_compile_job_store.mark_succeeded.assert_called_once()
        created_job = mock_compile_job_store.create.call_args.args[0]
        assert created_job.workspace_id == "ws_001"

    @pytest.mark.asyncio
    async def test_compile_replaces_converged_generating_orphan_session(self):
        """Do not reuse a converged session stuck in generating after restart."""
        old_session = MagicMock()
        old_session.id = "sess-stale-001"
        old_session.workspace_id = "ws_001"
        old_session.project_id = "p1"
        old_session.thread_id = "t1"
        old_session.round_count = 3
        old_session.action_items = []
        old_session.metadata = {
            "pipeline_stage": "generating",
            "last_round_status": "converged",
            "pipeline_stage_updated_at": (
                datetime.now(timezone.utc) - timedelta(minutes=11)
            ).isoformat(),
            "last_round_updated_at": (
                datetime.now(timezone.utc) - timedelta(minutes=12)
            ).isoformat(),
        }
        old_session.started_at = datetime.now(timezone.utc) - timedelta(minutes=20)

        closed_session = MagicMock()
        closed_session.id = "sess-closed-001"
        closed_session.workspace_id = "ws_001"
        closed_session.project_id = "p1"
        closed_session.thread_id = "t1"
        closed_session.is_active = False

        new_session = MagicMock()
        new_session.id = "sess-new-001"
        new_session.workspace_id = "ws_001"

        fake_result = FakeMeetingResult(
            session_id="sess-new-001",
            action_items=[{"title": "Build"}],
        )
        fake_running_compile_job = MagicMock()
        fake_running_compile_job.status = "running"
        fake_running_compile_job.updated_at = datetime.now(timezone.utc) - timedelta(
            minutes=11
        )

        mock_session_store = MagicMock()
        mock_session_store.list_by_workspace.return_value = [old_session, closed_session]
        mock_session_store.get_active_session.return_value = old_session
        mock_session_store.create.return_value = None

        mock_ms_cls = MagicMock()
        mock_ms_cls.new.return_value = new_session

        mock_compile_job_store = MagicMock()
        mock_compile_job_store.get_latest_for_session.return_value = (
            fake_running_compile_job
        )
        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = await _fake_result_run(fake_result)
        mock_engine_cls.return_value = mock_engine

        with install_fake_compile_modules(
            meeting_engine_cls=mock_engine_cls,
            session_store=mock_session_store,
            meeting_session_cls=mock_ms_cls,
            compile_job_store=mock_compile_job_store,
        ):
            result = await HandoffBundleService().intake_and_compile(
                bundle=make_handoff_bundle(),
                workspace=_workspace(),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

        assert result["status"] == "compiled"
        mock_session_store.close_stale_active_sessions.assert_called_once_with(
            "ws_001",
            project_id="p1",
            thread_id="t1",
            reason="stale_replaced_by_compile",
        )
        mock_compile_job_store.mark_incomplete_for_session.assert_has_calls(
            [
                call(
                    "sess-stale-001",
                    error="compile_session_replaced_by_new_intake",
                    metadata={"abort_reason": "stale_replaced_by_compile"},
                ),
                call(
                    "sess-closed-001",
                    error="compile_session_replaced_by_new_intake",
                    metadata={"abort_reason": "stale_replaced_by_compile"},
                ),
            ],
            any_order=True,
        )
        mock_session_store.end_session.assert_called_once_with(
            "sess-stale-001",
            state_after={"abort_reason": "stale_replaced_by_compile"},
        )
        mock_session_store.create.assert_called_once_with(new_session)
        created_job = mock_compile_job_store.create.call_args.args[0]
        assert created_job.session_id == "sess-new-001"

    @pytest.mark.asyncio
    async def test_compile_happy_path_no_task_ir(self):
        """Compile path where MeetingEngine produces no TaskIR."""
        fake_session = MagicMock()
        fake_session.id = "sess-hp-002"
        fake_session.workspace_id = "ws_001"
        fake_session.started_at = datetime.now(timezone.utc)
        fake_session.ended_at = None
        fake_session.status = "active"
        fake_session.metadata = {
            "last_round_updated_at": datetime.now(timezone.utc).isoformat()
        }

        mock_session_store = MagicMock()
        mock_session_store.list_by_workspace.return_value = []
        mock_session_store.get_active_session.return_value = fake_session
        mock_compile_job_store = MagicMock()
        mock_compile_job_store.get_latest_for_session.return_value = None

        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = await _fake_result_run(FakeMeetingResult(task_ir=None))
        mock_engine_cls.return_value = mock_engine

        with install_fake_compile_modules(
            meeting_engine_cls=mock_engine_cls,
            session_store=mock_session_store,
            compile_job_store=mock_compile_job_store,
        ):
            result = await HandoffBundleService().intake_and_compile(
                bundle=make_handoff_bundle(),
                workspace=_workspace(),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

        assert result["status"] == "compiled"
        assert result["compile_job_id"]
        assert result["task_ir_id"] is None
        assert result["persisted"] is False
        mock_engine_cls.assert_called_once()
        mock_session_store.get_active_session.assert_called_once_with(
            "ws_001",
            "p1",
            "t1",
        )
        mock_compile_job_store.create.assert_called_once()
        mock_compile_job_store.mark_succeeded.assert_called_once()
        created_job = mock_compile_job_store.create.call_args.args[0]
        assert created_job.workspace_id == "ws_001"

    @pytest.mark.asyncio
    async def test_compile_reuses_terminal_result_for_same_handoff_reentry(self):
        active_session = MagicMock()
        active_session.id = "sess-active-001"
        active_session.workspace_id = "ws_001"
        active_session.project_id = "p1"
        active_session.thread_id = "t1"
        active_session.started_at = datetime.now(timezone.utc)
        active_session.ended_at = None
        active_session.status = "active"
        active_session.metadata = {
            "last_round_updated_at": datetime.now(timezone.utc).isoformat()
        }

        existing_compile_job = MagicMock()
        existing_compile_job.id = "job-existing-001"
        existing_compile_job.handoff_id = "h_hp_001"
        existing_compile_job.session_id = "sess-active-001"
        existing_compile_job.status = "succeeded"
        existing_compile_job.result = {
            "status": "compiled",
            "compile_job_id": "job-existing-001",
            "job_id": "job-existing-001",
            "session_id": "sess-active-001",
            "task_ir_id": "task-existing-001",
            "persisted": True,
            "action_items_count": 2,
        }

        mock_session_store = MagicMock()
        mock_session_store.list_by_workspace.return_value = []
        mock_session_store.get_active_session.return_value = active_session
        mock_compile_job_store = MagicMock()
        mock_compile_job_store.get_latest_for_session.return_value = existing_compile_job
        mock_engine_cls = MagicMock()

        with install_fake_compile_modules(
            meeting_engine_cls=mock_engine_cls,
            session_store=mock_session_store,
            compile_job_store=mock_compile_job_store,
        ):
            result = await HandoffBundleService().intake_and_compile(
                bundle=make_handoff_bundle(),
                workspace=_workspace(),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

        assert result["compile_job_id"] == "job-existing-001"
        assert result["session_id"] == "sess-active-001"
        assert result["task_ir_id"] == "task-existing-001"
        assert result["persisted"] is True
        assert result["reused_compile_job"] is True
        mock_session_store.get_active_session.assert_called_once_with(
            "ws_001",
            "p1",
            "t1",
        )
        mock_compile_job_store.create.assert_not_called()
        mock_compile_job_store.mark_succeeded.assert_not_called()
        mock_engine_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_compile_aborts_superseded_active_session_for_new_handoff(self):
        superseded_session = MagicMock()
        superseded_session.id = "sess-old-001"
        superseded_session.workspace_id = "ws_001"
        superseded_session.project_id = "p1"
        superseded_session.thread_id = "t1"
        superseded_session.started_at = datetime.now(timezone.utc)
        superseded_session.ended_at = None
        superseded_session.status = "active"
        superseded_session.metadata = {
            "last_round_updated_at": datetime.now(timezone.utc).isoformat()
        }
        superseded_session.is_active = True

        old_compile_job = MagicMock()
        old_compile_job.id = "job-old-001"
        old_compile_job.handoff_id = "handoff-old-001"
        old_compile_job.session_id = "sess-old-001"
        old_compile_job.status = "running"

        new_session = MagicMock()
        new_session.id = "sess-new-001"
        new_session.workspace_id = "ws_001"
        new_session.project_id = "p1"
        new_session.thread_id = "t1"

        mock_session_store = MagicMock()
        mock_session_store.list_by_workspace.return_value = [superseded_session]
        mock_session_store.get_active_session.return_value = None

        mock_compile_job_store = MagicMock()
        mock_compile_job_store.get_latest_for_session.return_value = old_compile_job
        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = await _fake_result_run(
            FakeMeetingResult(session_id="sess-new-001")
        )
        mock_engine_cls.return_value = mock_engine

        mock_ms_cls = MagicMock()
        mock_ms_cls.new.return_value = new_session

        with install_fake_compile_modules(
            meeting_engine_cls=mock_engine_cls,
            session_store=mock_session_store,
            meeting_session_cls=mock_ms_cls,
            compile_job_store=mock_compile_job_store,
        ):
            result = await HandoffBundleService().intake_and_compile(
                bundle=make_handoff_bundle(),
                workspace=_workspace(),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

        assert result["status"] == "compiled"
        mock_compile_job_store.mark_incomplete_for_session.assert_any_call(
            "sess-old-001",
            error="compile_session_superseded_by_new_handoff",
            metadata={
                "abort_reason": "superseded_by_new_handoff",
                "superseded_by_handoff_id": "h_hp_001",
            },
        )
        superseded_session.abort.assert_called_once_with(
            reason="superseded_by_new_handoff"
        )
        assert superseded_session.metadata["superseded_by_handoff_id"] == "h_hp_001"
        mock_session_store.update.assert_called_once_with(superseded_session)
        mock_session_store.create.assert_called_once_with(new_session)
