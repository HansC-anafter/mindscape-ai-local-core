from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import MeetingCommandRecord, MeetingCommandStatus
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


def test_producer_quality_gate_strict_content_gate_blocks_accept_with_risk():
    gate = runner_module._producer_quality_gate_fallback(
        producer_review={
            "review_state": "passed",
            "review_reason": "producer_eval_passed",
            "recommended_actions": [],
        },
        producer_eval_summaries=[
            {
                "schema_version": "producer_eval_summary.v1",
                "producer": "performance_direction",
                "pack_code": "performance_direction",
                "playbook_code": "pd_storyboard_gen",
                "passed": False,
                "review_state": "needs_revision",
                "quality_gate_summary": {
                    "schema_version": "pd_storyboard_quality_gate_summary.v1",
                    "gate_stage": "content",
                    "strict_acceptance_required": True,
                    "storyboard_content_high_quality_pass": False,
                    "final_storyboard_high_quality_pass": False,
                    "meeting_final_acceptance_pass": False,
                    "failed_gate_ids": ["G4_LLM_SCENE_JUDGE"],
                },
            }
        ],
        quality_requirements={"strict_acceptance_required": True},
    )

    normalized = runner_module._normalize_meeting_quality_review(
        {
            "decision": "accept_with_risk",
            "rationale": "Accept despite the failed judge.",
            "recommended_actions": [],
        },
        fallback_gate=gate,
    )

    assert gate["strict_gate_failed"] is True
    assert gate["failed_gate_ids"] == ["G4_LLM_SCENE_JUDGE"]
    assert normalized["decision"] == "rewrite_required"
    assert normalized["completion_status"] == "needs_revision"


def test_producer_quality_gate_requires_eval_for_strict_storyboard_quality():
    gate = runner_module._producer_quality_gate_fallback(
        producer_review={
            "review_state": None,
            "review_reason": None,
            "recommended_actions": [],
        },
        producer_eval_summaries=[],
        quality_requirements={
            "target": {"deliverable_kind": "vertical_reels_storyboard"},
            "storyboard_content_high_quality_required": True,
        },
    )

    assert gate["gate_state"] == "blocked_for_revision"
    assert gate["decision"] == "producer_result_required"
    assert gate["completion_status"] == "needs_revision"
    assert gate["producer_result_missing"] is True
    assert gate["strict_gate_failed"] is True
    assert "PRODUCER_RESULT_REQUIRED" in gate["failed_gate_ids"]
    assert "resolve_producer_result:storyboard_quality_eval" in gate[
        "recommended_actions"
    ]


def test_dispatch_artifact_wait_honors_long_storyboard_timeout():
    command = MeetingCommandRecord(
        command_id="cmd_storyboard",
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        thread_id="thread_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Create a 90s reels storyboard with 45 scenes.",
        status=MeetingCommandStatus.RUNNING,
        metadata={"meeting_orchestration_timeout_seconds": 1800},
    )

    assert (
        MeetingEngineRunner._dispatch_artifact_wait_seconds(
            command=command,
            request_contract_aol={
                "quality_requirements": {
                    "target": {"deliverable_kind": "vertical_reels_storyboard"},
                    "content_quality": {"require_reference_grounding": True},
                }
            },
        )
        == 1800.0
    )


@pytest.mark.asyncio
async def test_meeting_engine_runner_blocks_strict_storyboard_without_dispatch_artifact(
    monkeypatch,
):
    class _FakeMeetingEngine:
        def __init__(self, **kwargs):
            self.session = kwargs["session"]

        async def run(self, message, handoff_in=None):
            self.session.metadata["request_contract"] = {
                "addressable_object_layer": {
                    "command_id": "cmd_runner",
                    "quality_requirements": {
                        "target": {"deliverable_kind": "vertical_reels_storyboard"},
                        "storyboard_content_high_quality_required": True,
                    },
                }
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
                                "execution_id": "exec-storyboard-pending",
                                "playbook_code": "pd_storyboard_gen",
                            }
                        }
                    }
                },
                completion_status="accepted",
            )

    async def _fake_persist_meeting_task_ir(task_ir):
        return None

    async def _fake_dispatch_artifact_refs(
        self,
        dispatch_result,
        *,
        artifacts_store,
        wait_seconds=None,
    ):
        return {
            "artifact_db_ids": [],
            "artifact_file_paths": [],
            "artifact_execution_errors": [],
            "artifact_file_path_missing_count": 0,
            "producer_eval_summaries": [],
        }

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
    monkeypatch.setattr(
        MeetingEngineRunner,
        "_dispatch_artifact_refs",
        _fake_dispatch_artifact_refs,
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
        message="Run strict 90s storyboard",
        handoff_in=SimpleNamespace(handoff_id="handoff_1"),
        command=_command(),
    )

    assert result["artifact_landing_status"] == "pending"
    assert result["producer_eval_summaries"] == []
    assert result["producer_quality_gate"]["decision"] == "producer_result_required"
    assert result["producer_quality_gate"]["producer_result_missing"] is True
    assert result["completion_status"] == "needs_revision"
