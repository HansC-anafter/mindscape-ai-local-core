from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import MeetingCommandRecord, MeetingCommandStatus
from backend.app.services.orchestration.meeting import meeting_engine_runner as runner_module
from backend.app.services.orchestration.meeting.meeting_engine_runner import (
    MeetingEngineRunner,
)


class _FakeRuntimeProfile:
    model_name = "runtime-model"
    default_model = None
    loop_budget = None
    recovery_policy = None

    def ensure_phase2_fields(self):
        return None


class _FakeWorkspaceRuntimeProfileStore:
    async def get_runtime_profile(self, workspace_id):
        return None

    async def create_default_profile(self, workspace_id):
        return _FakeRuntimeProfile()


class _FakeSessionStore:
    def __init__(self):
        self.updated = []

    def update(self, session):
        self.updated.append(session)
        return session


class _FakeArtifactsStore:
    def __init__(self):
        self.created = []
        self.by_id = {}
        self.by_execution_id = {}

    def get_artifact(self, artifact_id):
        return self.by_id.get(artifact_id)

    def get_by_execution_id(self, execution_id):
        artifacts = self.list_by_execution_id(execution_id)
        return artifacts[0] if artifacts else None

    def list_by_execution_id(self, execution_id):
        artifacts = self.by_execution_id.get(execution_id)
        if artifacts is None:
            return []
        if isinstance(artifacts, list):
            return artifacts
        return [artifacts]

    def create_artifact(self, artifact):
        self.created.append(artifact)
        self.by_id[artifact.id] = artifact
        return artifact


def _command() -> MeetingCommandRecord:
    return MeetingCommandRecord(
        command_id="cmd_runner",
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        thread_id="thread_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Run meeting orchestration",
        status=MeetingCommandStatus.ACCEPTED,
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
async def test_meeting_engine_runner_exposes_producer_eval_review_state(monkeypatch):
    captured = {"quality_review_prompts": []}

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
                    task_id="task_ir_quality",
                    artifacts=[
                        {
                            "id": "artifact_quality_eval",
                            "uri": "/tmp/content-quality.json",
                            "metadata": {
                                "file_path": "/tmp/content-quality.json",
                                "artifact_kind": (
                                    "performance_direction_storyboard_content_quality_eval"
                                ),
                                "producer_eval_summary": {
                                    "schema_version": "producer_eval_summary.v1",
                                    "producer": "performance_direction",
                                    "pack_code": "performance_direction",
                                    "playbook_code": "pd_storyboard_gen",
                                    "passed": False,
                                    "score": 52,
                                    "review_state": "needs_revision",
                                    "needs_revision": True,
                                    "rewrite_recommended": True,
                                    "rewrite_dispatch_request": {
                                        "schema_version": (
                                            "producer_quality_rewrite_dispatch_request.v1"
                                        ),
                                        "pack_code": "performance_direction",
                                        "playbook_code": (
                                            "pd_storyboard_content_rewrite"
                                        ),
                                    },
                                    "recommended_actions": [
                                        "rewrite_storyboard_script_with_reference_cues"
                                    ],
                                },
                            },
                        }
                    ],
                ),
                dispatch_result={"status": "dispatched"},
                completion_status="accepted",
            )

        async def _generate_text(self, messages, **kwargs):
            captured["quality_review_prompts"].append(
                {"messages": messages, "kwargs": kwargs}
            )
            return """
            {
              "decision": "rewrite_required",
              "rationale": "Scene copy is too generic for the selected references.",
              "recommended_actions": [
                "rewrite_storyboard_script_with_reference_cues",
                "preserve_scene_count"
              ],
              "rewrite_instructions": [
                "Add reference-specific visual cues to every scene.",
                "Make each scene carry a distinct narrative function."
              ],
              "required_reference_questions": []
            }
            """

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

    assert result["artifact_landing_status"] == "landed"
    assert result["producer_eval_summaries"][0]["review_state"] == "needs_revision"
    assert result["producer_eval_summaries"][0]["artifact_id"] == "artifact_quality_eval"
    assert result["review_state"] == "needs_revision"
    assert result["review_reason"] == "producer_eval_requires_review"
    assert (
        "rewrite_storyboard_script_with_reference_cues"
        in result["recommended_actions"]
    )
    assert "accept_with_risk" in result["recommended_actions"]
    assert result["completion_status"] == "needs_revision"
    assert result["producer_quality_gate"]["schema_version"] == (
        "meeting_producer_quality_gate.v1"
    )
    assert result["producer_quality_gate"]["llm_review_status"] == "completed"
    assert result["producer_quality_gate"]["gate_state"] == "blocked_for_revision"
    assert result["producer_quality_gate"]["decision"] == "rewrite_required"
    assert "preserve_scene_count" in result["producer_quality_gate"]["recommended_actions"]
    assert result["producer_quality_gate"]["rewrite_handoff"]["kind"] == (
        "producer_quality_rewrite_handoff"
    )
    assert result["producer_quality_gate"]["rewrite_handoff"]["dispatch_request"][
        "playbook_code"
    ] == "pd_storyboard_content_rewrite"
    assert result["producer_quality_gate"]["rewrite_handoff"]["dispatch_request"][
        "dispatch_mode"
    ] == "explicit_quality_requirement_required"
    assert result["producer_quality_gate"]["rewrite_handoff"]["meeting_review"][
        "rewrite_instructions"
    ] == [
        "Add reference-specific visual cues to every scene.",
        "Make each scene carry a distinct narrative function.",
    ]
    assert len(captured["quality_review_prompts"]) == 1
    assert "Producer eval summaries" in captured["quality_review_prompts"][0]["messages"][1]["content"]


def test_producer_quality_gate_dispatch_request_respects_rewrite_requirement():
    gate = runner_module._producer_quality_gate_fallback(
        producer_review={
            "review_state": "needs_revision",
            "review_reason": "producer_eval_requires_review",
            "recommended_actions": [
                "rewrite_storyboard_script_with_reference_cues"
            ],
        },
        producer_eval_summaries=[
            {
                "schema_version": "producer_eval_summary.v1",
                "producer": "performance_direction",
                "pack_code": "performance_direction",
                "playbook_code": "pd_storyboard_gen",
                "artifact_id": "artifact_quality_eval",
                "passed": False,
                "review_state": "needs_revision",
                "rewrite_recommended": True,
                "rewrite_dispatch_request": {
                    "schema_version": "producer_quality_rewrite_dispatch_request.v1",
                    "pack_code": "performance_direction",
                    "playbook_code": "pd_storyboard_content_rewrite",
                },
            }
        ],
        quality_requirements={"rewrite_until_quality_passed": True},
    )

    dispatch_request = gate["rewrite_handoff"]["dispatch_request"]
    assert dispatch_request["schema_version"] == (
        "producer_quality_rewrite_dispatch_request.v1"
    )
    assert dispatch_request["pack_code"] == "performance_direction"
    assert dispatch_request["playbook_code"] == "pd_storyboard_content_rewrite"
    assert dispatch_request["dispatch_mode"] == "auto_launch_allowed"
    assert dispatch_request["input_params"]["producer_eval_artifact_ids"] == [
        "artifact_quality_eval"
    ]


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
