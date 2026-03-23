import asyncio
from types import SimpleNamespace

from backend.app.services.conversation.task_manager_core.artifacts import (
    attach_artifact_to_timeline_item,
    resolve_task_intent_id,
    update_artifact_latest_markers,
)


class FakeTimelineItemsStore:
    def __init__(self):
        self.updated = []

    def update_timeline_item(self, item_id, data):
        self.updated.append((item_id, data))


class FakeArtifactsStore:
    def __init__(self, artifacts=None):
        self.artifacts = {artifact.id: artifact for artifact in (artifacts or [])}
        self.updated = []

    def list_artifacts_by_playbook(self, workspace_id, playbook_code):
        return list(self.artifacts.values())

    def get_artifact(self, artifact_id):
        return self.artifacts.get(artifact_id)

    def update_artifact(self, artifact_id, metadata):
        self.updated.append((artifact_id, metadata))
        if artifact_id in self.artifacts:
            self.artifacts[artifact_id].metadata = metadata


class FakeWorkspaces:
    def __init__(self, workspace):
        self.workspace = workspace

    async def get_workspace(self, workspace_id):
        return self.workspace


class FakeStore:
    def __init__(self, workspace):
        self.workspaces = FakeWorkspaces(workspace)


def test_resolve_task_intent_id_uses_result_then_metadata():
    task = SimpleNamespace(intent_id="intent-from-task", metadata={"intent_id": "meta"})
    assert resolve_task_intent_id(task, {"intent_id": "result"}) == "result"
    assert resolve_task_intent_id(task, {}) == "intent-from-task"

    task_without_attr = SimpleNamespace(metadata={"intent_id": "meta"})
    assert resolve_task_intent_id(task_without_attr, {}) == "meta"


def test_update_artifact_latest_markers_flips_old_versions():
    old_artifact = SimpleNamespace(
        id="old",
        artifact_type=SimpleNamespace(value="draft"),
        metadata={"is_latest": True},
    )
    same_new = SimpleNamespace(
        id="new",
        artifact_type=SimpleNamespace(value="draft"),
        metadata={"is_latest": False},
    )
    other_type = SimpleNamespace(
        id="other",
        artifact_type=SimpleNamespace(value="summary"),
        metadata={"is_latest": True},
    )
    store = FakeArtifactsStore([old_artifact, same_new, other_type])

    update_artifact_latest_markers(
        artifacts_store=store,
        workspace_id="ws-1",
        playbook_code="planning",
        artifact_type="draft",
        new_artifact_id="new",
    )

    assert ("old", {"is_latest": False}) in store.updated
    assert ("new", {"is_latest": True}) in store.updated
    assert all(update[0] != "other" for update in store.updated)


def test_attach_artifact_to_timeline_item_records_storage_warning():
    task = SimpleNamespace(id="task-1", workspace_id="ws-1", metadata={})
    timeline_item = SimpleNamespace(id="tl-1", data={})
    timeline_items_store = FakeTimelineItemsStore()
    workspace = SimpleNamespace(storage_base_path=None, storage_config={})

    result = asyncio.run(
        attach_artifact_to_timeline_item(
            store=FakeStore(workspace),
            artifacts_store=object(),
            timeline_items_store=timeline_items_store,
            artifact_extractor=object(),
            task=task,
            timeline_item=timeline_item,
            execution_result={},
            playbook_code="planning",
            get_next_version_fn=lambda **kwargs: 1,
            update_latest_markers_fn=lambda **kwargs: None,
            create_mind_event_fn=lambda **kwargs: None,
        )
    )

    assert result is None
    assert timeline_item.data["artifact_creation_failed"] is True
    assert timeline_item.data["artifact_warning"]["type"] == "storage_path_not_configured"
    assert timeline_items_store.updated
