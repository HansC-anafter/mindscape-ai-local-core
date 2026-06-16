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
async def test_meeting_engine_runner_reconciles_dispatch_execution_artifacts(monkeypatch):
    class _FakeMeetingEngine:
        def __init__(self, **kwargs):
            self.session = kwargs["session"]

        async def run(self, message, handoff_in=None):
            self.session.metadata["request_contract"] = {
                "addressable_object_layer": {"command_id": "cmd_runner"}
            }
            return runner_module.MeetingResult(
                session_id="mtg_demo",
                minutes_md="minutes",
                decision="accepted",
                event_ids=[],
                task_ir=SimpleNamespace(task_id="task_ir_dispatch", artifacts=[]),
                dispatch_result={
                    "attempts": {
                        "phase_1": {
                            "result": {
                                "execution_id": "exec-dispatch-1",
                                "playbook_code": "storyboard_generation_workflow",
                            }
                        }
                    }
                },
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

    artifacts_store = _FakeArtifactsStore()
    artifacts_store.by_execution_id["exec-dispatch-1"] = SimpleNamespace(
        id="artifact-dispatch-1",
        storage_ref=None,
        metadata={"file_path": "/tmp/dispatch-artifact.json"},
    )

    result = await MeetingEngineRunner(
        store=SimpleNamespace(name="mindscape_store", artifacts=artifacts_store),
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

    assert result["artifact_ids"] == ["artifact-dispatch-1"]
    assert result["artifact_db_ids"] == ["artifact-dispatch-1"]
    assert result["artifact_file_paths"] == ["/tmp/dispatch-artifact.json"]
    assert result["artifact_landing_status"] == "landed"


@pytest.mark.asyncio
async def test_meeting_engine_runner_reconciles_multiple_dispatch_artifacts(monkeypatch):
    class _FakeMeetingEngine:
        def __init__(self, **kwargs):
            self.session = kwargs["session"]

        async def run(self, message, handoff_in=None):
            return runner_module.MeetingResult(
                session_id="mtg_demo",
                minutes_md="minutes",
                decision="accepted",
                event_ids=[],
                task_ir=SimpleNamespace(task_id="task_ir_dispatch", artifacts=[]),
                dispatch_result={
                    "attempts": {
                        "phase_1": {
                            "result": {
                                "execution_id": "exec-dispatch-multi",
                                "playbook_code": "generic_output_playbook",
                            }
                        }
                    }
                },
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

    artifacts_store = _FakeArtifactsStore()
    artifacts_store.by_execution_id["exec-dispatch-multi"] = [
        SimpleNamespace(
            id="artifact-proposal",
            storage_ref="/tmp/landing-dir",
            metadata={"actual_file_path": "/tmp/proposal.md"},
        ),
        SimpleNamespace(
            id="artifact-manifest",
            storage_ref=None,
            metadata={"actual_file_path": "/tmp/manifest.json"},
        ),
    ]
    result = await MeetingEngineRunner(
        store=SimpleNamespace(name="mindscape_store", artifacts=artifacts_store),
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

    assert result["artifact_ids"] == ["artifact-proposal", "artifact-manifest"]
    assert result["artifact_db_ids"] == ["artifact-proposal", "artifact-manifest"]
    assert result["artifact_file_paths"] == ["/tmp/proposal.md", "/tmp/manifest.json"]
    assert "/tmp/landing-dir" not in result["artifact_file_paths"]
    assert result["artifact_landing_status"] == "landed"


@pytest.mark.asyncio
async def test_meeting_engine_runner_retries_dispatch_artifacts_until_file_paths_exist():
    class _EventuallyCompleteArtifactsStore:
        def __init__(self):
            self.calls = 0

        def list_by_execution_id(self, execution_id):
            self.calls += 1
            proposal_metadata = {}
            if self.calls > 1:
                proposal_metadata = {"actual_file_path": "/tmp/proposal.md"}
            return [
                SimpleNamespace(
                    id="artifact-proposal",
                    storage_ref=None,
                    metadata=proposal_metadata,
                ),
                SimpleNamespace(
                    id="artifact-manifest",
                    storage_ref=None,
                    metadata={"actual_file_path": "/tmp/manifest.json"},
                ),
            ]

    artifacts_store = _EventuallyCompleteArtifactsStore()
    result = await MeetingEngineRunner(
        store=SimpleNamespace(name="mindscape_store", artifacts=artifacts_store),
        session_store=_FakeSessionStore(),
    )._dispatch_artifact_refs(
        {"attempts": {"phase_1": {"result": {"execution_id": "exec-dispatch-race"}}}},
        artifacts_store=artifacts_store,
    )

    assert artifacts_store.calls == 2
    assert result["artifact_db_ids"] == ["artifact-proposal", "artifact-manifest"]
    assert result["artifact_file_paths"] == ["/tmp/proposal.md", "/tmp/manifest.json"]
    assert result["artifact_file_path_missing_count"] == 0
    assert (
        MeetingEngineRunner._artifact_landing_status(
            artifact_ids=["artifact-proposal", "artifact-manifest"],
            artifact_db_ids=["artifact-proposal", "artifact-manifest"],
            artifact_file_paths=["/tmp/manifest.json"],
            artifact_missing_file_paths=1,
        )
        == "pending"
    )


@pytest.mark.asyncio
async def test_meeting_engine_runner_does_not_land_failed_dispatch_execution_artifacts(monkeypatch):
    class _FakeMeetingEngine:
        def __init__(self, **kwargs):
            self.session = kwargs["session"]

        async def run(self, message, handoff_in=None):
            return runner_module.MeetingResult(
                session_id="mtg_demo",
                minutes_md="minutes",
                decision="accepted",
                event_ids=[],
                task_ir=SimpleNamespace(task_id="task_ir_dispatch", artifacts=[]),
                dispatch_result={
                    "attempts": {
                        "phase_1": {
                            "result": {
                                "execution_id": "exec-dispatch-failed",
                                "playbook_code": "generic_output_playbook",
                            }
                        }
                    }
                },
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

    artifacts_store = _FakeArtifactsStore()
    artifacts_store.by_execution_id["exec-dispatch-failed"] = SimpleNamespace(
        id="artifact-dispatch-failed",
        storage_ref="/tmp/failed-wrapper",
        metadata={},
        content={
            "status": "completed",
            "steps": {
                "generate_output": {
                    "status": "error",
                    "error": "Step generate_output tool error: boom",
                }
            },
        },
    )

    result = await MeetingEngineRunner(
        store=SimpleNamespace(name="mindscape_store", artifacts=artifacts_store),
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

    assert result["artifact_ids"] == []
    assert result["artifact_db_ids"] == []
    assert result["artifact_file_paths"] == []
    assert result["artifact_landing_status"] == "failed"
    assert result["artifact_execution_errors"] == [
        {
            "execution_id": "exec-dispatch-failed",
            "artifact_id": "artifact-dispatch-failed",
            "error": "step_failed:generate_output:Step generate_output tool error: boom",
        }
    ]
