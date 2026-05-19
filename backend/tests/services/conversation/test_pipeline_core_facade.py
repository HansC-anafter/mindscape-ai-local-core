from types import SimpleNamespace

import pytest

from backend.app.services.conversation import pipeline_core
from backend.app.services.conversation.pipeline_core import PipelineCore, PipelineResult
from backend.app.services.conversation.pipeline_core_core.artifacts import (
    append_unique,
    artifact_file_path,
    clean_string,
    task_ir_artifact_payloads,
)


def test_pipeline_result_defaults_preserve_response_shape():
    result = PipelineResult()

    assert result.events == []
    assert result.response_text == ""
    assert result.suggestion_cards == []
    assert result.task_ir_artifacts == []
    assert result.artifact_ids == []
    assert result.artifact_file_paths == []
    assert result.success is True
    assert result.error is None


def test_pipeline_core_preserves_public_method_surface():
    required = ["process", "_emit_pipeline_stage"]

    assert [name for name in required if not hasattr(PipelineCore, name)] == []


def test_task_ir_artifact_helpers_preserve_extraction_rules():
    class ArtifactModel:
        def model_dump(self, exclude_none=True):
            return {
                "id": " artifact-1 ",
                "metadata": {"file_path": " /tmp/artifact-one.txt "},
            }

    task_ir = SimpleNamespace(
        artifacts=[
            ArtifactModel(),
            {"id": "artifact-2", "uri": "/tmp/artifact-two.txt"},
        ]
    )

    payloads = task_ir_artifact_payloads(task_ir)
    artifact_ids = []
    artifact_paths = []

    for payload in payloads:
        append_unique(artifact_ids, clean_string(payload.get("id")))
        append_unique(artifact_paths, artifact_file_path(payload))

    append_unique(artifact_ids, "artifact-2")

    assert artifact_ids == ["artifact-1", "artifact-2"]
    assert artifact_paths == ["/tmp/artifact-one.txt", "/tmp/artifact-two.txt"]


@pytest.mark.asyncio
async def test_pipeline_core_process_delegates_to_runtime(monkeypatch):
    called = {}

    async def fake_process_pipeline(**kwargs):
        called.update(kwargs)
        return "runtime-result"

    monkeypatch.setattr(pipeline_core, "process_pipeline", fake_process_pipeline)
    core = PipelineCore.__new__(PipelineCore)

    result = await PipelineCore.process(
        core,
        workspace_id="workspace-1",
        profile_id="profile-1",
        thread_id="thread-1",
        project_id="project-1",
        message="Hello",
        user_event_id="event-1",
        execution_mode="qa",
        model_name="model-1",
        request=None,
    )

    assert result == "runtime-result"
    assert called["pipeline"] is core
    assert called["result_factory"] is PipelineResult
    assert called["workspace_id"] == "workspace-1"
    assert called["thread_id"] == "thread-1"


@pytest.mark.asyncio
async def test_pipeline_core_emit_stage_delegates_to_event_module(monkeypatch):
    called = {}

    async def fake_emit_pipeline_stage(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(pipeline_core, "emit_pipeline_stage", fake_emit_pipeline_stage)
    core = PipelineCore.__new__(PipelineCore)

    await PipelineCore._emit_pipeline_stage(
        core,
        "workspace-1",
        "profile-1",
        "thread-1",
        "project-1",
        "context_building",
        "Preparing context.",
        "run-1",
    )

    assert called["pipeline"] is core
    assert called["workspace_id"] == "workspace-1"
    assert called["stage"] == "context_building"
    assert called["run_id"] == "run-1"
