import importlib

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType


class _NoopMindscapeStore:
    pass


def test_artifact_to_response_exposes_task_id():
    mindscape_store = importlib.import_module("backend.app.services.mindscape_store")
    original_store = mindscape_store.MindscapeStore
    mindscape_store.MindscapeStore = _NoopMindscapeStore
    try:
        artifact_routes = importlib.import_module("backend.app.routes.core.artifacts")
    finally:
        mindscape_store.MindscapeStore = original_store

    artifact = Artifact(
        id="artifact_demo",
        workspace_id="ws_demo",
        task_id="task_demo",
        execution_id="exec_demo",
        thread_id="thread_demo",
        playbook_code="pd_storyboard_gen",
        artifact_type=ArtifactType.DATA,
        title="Storyboard manifest",
        summary="Generated storyboard manifest",
        content={"storyboard": {"storyboard_id": "sb_demo"}},
        storage_ref=None,
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata={"artifact_kind": "performance_direction_storyboard_manifest"},
    )

    response = artifact_routes.artifact_to_response(artifact)

    assert response.task_id == "task_demo"
    assert response.execution_id == "exec_demo"
    assert response.thread_id == "thread_demo"
