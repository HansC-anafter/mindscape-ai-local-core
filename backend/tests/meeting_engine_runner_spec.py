from types import SimpleNamespace

import pytest

from backend.app.services.orchestration.meeting import meeting_engine_runner as runner_module
from backend.app.services.orchestration.meeting.meeting_engine_runner import (
    MeetingEngineRunner,
)
from backend.tests.meeting_engine_runner_support import (
    _FakeArtifactsStore,
    _FakeSessionStore,
    _FakeWorkspaceRuntimeProfileStore,
    _command,
)


@pytest.mark.asyncio
async def test_meeting_engine_runner_persists_task_ir_and_session_aol_metadata(monkeypatch):
    captured = {"engines": [], "persisted_task_ir": []}

    class _FakeMeetingEngine:
        def __init__(self, **kwargs):
            captured["engines"].append(kwargs)

        async def run(self, message, handoff_in=None):
            session = captured["engines"][0]["session"]
            session.metadata["request_contract"] = {
                "addressable_object_layer": {
                    "command_id": "cmd_runner",
                    "selected_guidance_ids": ["guidance-1"],
                }
            }
            task_ir = SimpleNamespace(
                task_id="task_ir_runner",
                artifacts=[
                    {
                        "id": "artifact_1",
                        "uri": "/tmp/meeting-output.md",
                        "metadata": {"file_path": "/tmp/meeting-output.md"},
                    }
                ],
            )
            return runner_module.MeetingResult(
                session_id="mtg_demo",
                minutes_md="minutes",
                decision="accepted",
                event_ids=["evt_1"],
                task_ir=task_ir,
                dispatch_result={"status": "dispatched"},
                completion_status="accepted",
            )

    async def _fake_persist_meeting_task_ir(task_ir):
        captured["persisted_task_ir"].append(task_ir)

    monkeypatch.setattr(
        "backend.app.services.stores.workspace_runtime_profile_store.WorkspaceRuntimeProfileStore",
        _FakeWorkspaceRuntimeProfileStore,
    )
    monkeypatch.setattr(runner_module, "MeetingEngine", _FakeMeetingEngine)
    monkeypatch.setattr(
        "backend.app.services.conversation.pipeline_meeting.build_execution_launcher",
        lambda store: SimpleNamespace(store=store),
    )
    monkeypatch.setattr(
        "backend.app.services.conversation.pipeline_meeting.persist_meeting_task_ir",
        _fake_persist_meeting_task_ir,
    )

    session = SimpleNamespace(
        id="mtg_demo",
        thread_id="thread_demo",
        project_id="project_demo",
        metadata={},
    )
    workspace = SimpleNamespace(
        id="ws_demo",
        owner_user_id="profile_demo",
        primary_project_id="project_demo",
        metadata={},
        resolved_executor_runtime="local_executor",
    )
    session_store = _FakeSessionStore()
    artifacts_store = _FakeArtifactsStore()
    result = await MeetingEngineRunner(
        store=SimpleNamespace(name="mindscape_store", artifacts=artifacts_store),
        session_store=session_store,
    ).run_meeting_orchestration(
        session=session,
        workspace=workspace,
        message="Run meeting orchestration",
        handoff_in=SimpleNamespace(handoff_id="handoff_1"),
        command=_command(),
    )

    assert result["status"] == "completed"
    assert result["task_ir_id"] == "task_ir_runner"
    assert result["artifact_ids"] == ["artifact_1"]
    assert result["artifact_file_paths"] == ["/tmp/meeting-output.md"]
    assert result["artifact_db_ids"] == ["artifact_1"]
    assert result["artifact_db_errors"] == []
    assert result["artifact_landing_status"] == "landed"
    assert result["request_contract_aol_metadata"] == {
        "command_id": "cmd_runner",
        "selected_guidance_ids": ["guidance-1"],
    }
    assert result["request_contract_aol_metadata_persisted"] is True
    assert captured["persisted_task_ir"][0].task_id == "task_ir_runner"
    assert session_store.updated == [session]
    [engine_kwargs] = captured["engines"]
    assert engine_kwargs["profile_id"] == "profile_demo"
    assert engine_kwargs["thread_id"] == "thread_demo"
    assert engine_kwargs["project_id"] == "project_demo"
    assert engine_kwargs["model_name"] == "runtime-model"
    assert engine_kwargs["execution_context"].route_kind == "meeting"
    assert engine_kwargs["execution_context"].execution_profile == "durable"
    [landed_artifact] = artifacts_store.created
    assert landed_artifact.id == "artifact_1"
    assert landed_artifact.workspace_id == "ws_demo"
    assert landed_artifact.task_id == "task_ir_runner"
    assert landed_artifact.thread_id == "thread_demo"
    assert landed_artifact.storage_ref == "/tmp/meeting-output.md"
    assert landed_artifact.metadata["meeting_id"] == "mtg_demo"
    assert landed_artifact.metadata["command_id"] == "cmd_runner"
    assert landed_artifact.metadata["request_contract_aol_metadata"] == {
        "command_id": "cmd_runner",
        "selected_guidance_ids": ["guidance-1"],
    }


@pytest.mark.asyncio
async def test_meeting_engine_runner_marks_artifact_landing_pending_without_artifact_store(monkeypatch):
    class _FakeMeetingEngine:
        def __init__(self, **kwargs):
            self.session = kwargs["session"]

        async def run(self, message, handoff_in=None):
            return runner_module.MeetingResult(
                session_id="mtg_demo",
                minutes_md="minutes",
                decision="accepted",
                event_ids=[],
                task_ir=SimpleNamespace(
                    task_id="task_ir_pending",
                    artifacts=[
                        {
                            "id": "artifact_pending",
                            "type": "text/markdown",
                            "uri": "/tmp/pending.md",
                            "metadata": {"file_path": "/tmp/pending.md"},
                        }
                    ],
                ),
                dispatch_result={},
                completion_status="accepted",
            )

    async def _fake_persist_meeting_task_ir(task_ir):
        return None

    monkeypatch.setattr(
        "backend.app.services.stores.workspace_runtime_profile_store.WorkspaceRuntimeProfileStore",
        _FakeWorkspaceRuntimeProfileStore,
    )
    monkeypatch.setattr(runner_module, "MeetingEngine", _FakeMeetingEngine)
    monkeypatch.setattr(
        "backend.app.services.conversation.pipeline_meeting.build_execution_launcher",
        lambda store: SimpleNamespace(store=store),
    )
    monkeypatch.setattr(
        "backend.app.services.conversation.pipeline_meeting.persist_meeting_task_ir",
        _fake_persist_meeting_task_ir,
    )

    result = await MeetingEngineRunner(
        store=SimpleNamespace(name="mindscape_store"),
        session_store=_FakeSessionStore(),
    ).run_meeting_orchestration(
        session=SimpleNamespace(
            id="mtg_demo",
            thread_id="thread_demo",
            project_id="project_demo",
            metadata={},
        ),
        workspace=SimpleNamespace(
            id="ws_demo",
            owner_user_id="profile_demo",
            primary_project_id="project_demo",
            metadata={},
            resolved_executor_runtime="local_executor",
        ),
        message="Run meeting orchestration",
        handoff_in=SimpleNamespace(handoff_id="handoff_1"),
        command=_command(),
    )

    assert result["artifact_ids"] == ["artifact_pending"]
    assert result["artifact_file_paths"] == ["/tmp/pending.md"]
    assert result["artifact_db_ids"] == []
    assert result["artifact_landing_status"] == "pending"
    assert result["artifact_db_errors"] == [
        {
            "code": "artifact_store_unavailable",
            "message": "MindscapeStore.artifacts is unavailable; TaskIR artifacts remain pending DB landing.",
        }
    ]
