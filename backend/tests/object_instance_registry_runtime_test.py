import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import backend.app as backend_app

sys.modules["app"] = backend_app

from backend.app.models.object_runtime import (
    ObjectGraphProjectRequest,
    ObjectInstanceRecord,
    ObjectInstanceSyncRequest,
    ObjectReadRequest,
    ObjectRelationIndexRequest,
    ObjectRelationRecord,
    ObjectRef,
)


def _load_object_runtime_module():
    workspace_dir = REPO_ROOT / "backend" / "app" / "routes" / "core" / "workspace"
    package_name = "backend.app.routes.core.workspace"
    if package_name not in sys.modules:
        workspace_package = types.ModuleType(package_name)
        workspace_package.__path__ = [str(workspace_dir)]
        sys.modules[package_name] = workspace_package

    module_path = workspace_dir / "object_runtime.py"
    module_name = "backend.app.routes.core.workspace.object_runtime_registry_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


object_runtime_module = _load_object_runtime_module()


def _storyboard_record() -> ObjectInstanceRecord:
    return ObjectInstanceRecord(
        ref=ObjectRef(
            uri="mindscape://performance_direction/storyboard_scene/pd_session_1:latest:sc02",
            owner_pack="performance_direction",
            object_kind="storyboard_scene",
            object_id="pd_session_1:latest:sc02",
            workspace_id="ws_demo",
            selector={
                "selector_type": "storyboard_scene",
                "scene_id": "sc02",
            },
        ),
        title="Yoga storyboard / sc02",
        subtitle="performance_direction storyboard scene",
        summary_text="A concrete storyboard scene target.",
        labels=["storyboard", "scene"],
        mention_tokens=["@storyboard_scene:pd_session_1:latest:sc02"],
        mention_text="pd performance direction storyboard scene sc02",
        affordance_verbs=["patch_storyboard"],
    )


def test_object_completion_item_preserves_token_ref_and_affordance_metadata():
    item = object_runtime_module._to_mention_completion_item(
        _storyboard_record(),
        query="storyboard",
    )

    assert item.token == "@storyboard_scene:pd_session_1:latest:sc02"
    assert item.label == "Yoga storyboard / sc02"
    assert item.ref.selector == {
        "selector_type": "storyboard_scene",
        "scene_id": "sc02",
        "metadata": {},
    }
    assert item.metadata["affordance_verbs"] == ["patch_storyboard"]


@pytest.mark.asyncio
async def test_complete_workspace_objects_uses_registry_backed_records(monkeypatch):
    captured = {}

    class FakeObjectInstanceStore:
        def search(self, **kwargs):
            captured.update(kwargs)
            return [_storyboard_record()]

    async def fake_ensure_workspace_exists(workspace_id: str) -> None:
        assert workspace_id == "ws_demo"

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_instance_registry_store",
        lambda: FakeObjectInstanceStore(),
    )

    response = await object_runtime_module.complete_workspace_objects(
        workspace_id="ws_demo",
        query="storyboard",
        owner_pack="performance_direction",
        object_kind="storyboard_scene",
        limit=10,
    )

    assert captured == {
        "workspace_id": "ws_demo",
        "query": "storyboard",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "limit": 10,
    }
    assert response.results[0].ref.object_kind == "storyboard_scene"
    assert response.results[0].token == "@storyboard_scene:pd_session_1:latest:sc02"


@pytest.mark.asyncio
async def test_read_workspace_object_accepts_uri_only_json_ref(monkeypatch):
    captured = {}
    record = _storyboard_record()

    class FakeCatalogRegistry:
        def get_entry(self, owner_pack: str, object_kind: str):
            assert owner_pack == "performance_direction"
            assert object_kind == "storyboard_scene"
            return {
                "owner_pack": owner_pack,
                "object_kind": object_kind,
                "display_name": "Storyboard Scene",
                "id_field": "id",
                "summary_fields": ["title"],
                "supports": ["summary"],
            }

    class FakeObjectInstanceStore:
        def get_by_uri(self, **kwargs):
            captured.update(kwargs)
            return record

    async def fake_ensure_workspace_exists(workspace_id: str) -> None:
        assert workspace_id == "ws_demo"

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_instance_registry_store",
        lambda: FakeObjectInstanceStore(),
    )

    response = await object_runtime_module.read_workspace_object(
        request=ObjectReadRequest(object_ref={"uri": record.ref.uri}),
        workspace_id="ws_demo",
    )

    assert captured == {
        "workspace_id": "ws_demo",
        "uri": record.ref.uri,
    }
    assert response.object.ref.uri == record.ref.uri
    assert response.object.title == "Yoga storyboard / sc02"


@pytest.mark.asyncio
async def test_sync_workspace_object_index_delegates_to_sync_service(monkeypatch):
    captured = {}

    async def fake_ensure_workspace_exists(workspace_id: str) -> None:
        assert workspace_id == "ws_demo"

    class FakeObjectIndexSyncService:
        async def sync_workspace(self, workspace_id, request):
            captured["workspace_id"] = workspace_id
            captured["request"] = request
            return object_runtime_module.ObjectInstanceSyncResponse(
                workspace_id=workspace_id,
                indexed_count=7,
                sources=[],
            )

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "get_object_index_sync_service",
        lambda: FakeObjectIndexSyncService(),
    )

    response = await object_runtime_module.sync_workspace_object_index(
        request=ObjectInstanceSyncRequest(owner_pack="performance_direction"),
        workspace_id="ws_demo",
    )

    assert response.indexed_count == 7
    assert captured["workspace_id"] == "ws_demo"
    assert captured["request"].owner_pack == "performance_direction"


@pytest.mark.asyncio
async def test_index_and_search_workspace_object_relations_use_registry(monkeypatch):
    captured_relations = []

    source_ref = ObjectRef(
        uri="mindscape://ig/reference/ref_001",
        owner_pack="ig",
        object_kind="reference",
        object_id="ref_001",
        workspace_id="ws_demo",
    )
    target_ref = _storyboard_record().ref
    relation = ObjectRelationRecord(
        source_ref=source_ref,
        relation_kind="planned_input_for",
        target_ref=target_ref,
        source_role="source",
        target_role="target",
        provenance_type="object_action_plan",
        provenance_id="oap_demo",
    )

    class FakeObjectRelationStore:
        def upsert_many(self, workspace_id, relations):
            assert workspace_id == "ws_demo"
            captured_relations.extend(relations)
            return len(relations)

        def search(self, **kwargs):
            assert kwargs == {
                "workspace_id": "ws_demo",
                "object_uri": source_ref.uri,
                "source_uri": None,
                "target_uri": None,
                "relation_kind": None,
                "meeting_id": None,
                "limit": 100,
            }
            return [relation]

    async def fake_ensure_workspace_exists(workspace_id: str) -> None:
        assert workspace_id == "ws_demo"

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: FakeObjectRelationStore(),
    )

    index_response = await object_runtime_module.index_workspace_object_relations(
        request=ObjectRelationIndexRequest(relations=[relation]),
        workspace_id="ws_demo",
    )
    search_response = await object_runtime_module.search_workspace_object_relations(
        workspace_id="ws_demo",
        object_uri=source_ref.uri,
        source_uri=None,
        target_uri=None,
        relation_kind=None,
        meeting_id=None,
        limit=100,
    )

    assert index_response.indexed_count == 1
    assert captured_relations[0].relation_kind == "planned_input_for"
    assert search_response.results[0].provenance_id == "oap_demo"


@pytest.mark.asyncio
async def test_project_object_graph_uses_registry_relations_without_pack_backend(monkeypatch):
    output_ref = ObjectRef(
        uri="mindscape://performance_direction/generated_reels_asset/gra_001",
        owner_pack="performance_direction",
        object_kind="generated_reels_asset",
        object_id="gra_001",
        workspace_id="ws_demo",
    )
    source_ref = ObjectRef(
        uri="mindscape://ig/reference/ref_001",
        owner_pack="ig",
        object_kind="reference",
        object_id="ref_001",
        workspace_id="ws_demo",
    )
    relation = ObjectRelationRecord(
        source_ref=source_ref,
        relation_kind="generated_from_source",
        target_ref=output_ref,
        provenance_type="object_action_execution",
        provenance_id="oap_demo",
    )

    class FakeCatalogRegistry:
        def get_entry(self, owner_pack: str, object_kind: str):
            return {
                "owner_pack": owner_pack,
                "object_kind": object_kind,
                "display_name": object_kind.replace("_", " ").title(),
                "id_field": "id",
                "summary_fields": ["object_id"],
                "supports": ["summary"],
            }

    class FakeObjectRelationStore:
        def search(self, **kwargs):
            assert kwargs == {
                "workspace_id": "ws_demo",
                "object_uri": output_ref.uri,
                "limit": 100,
            }
            return [relation]

    async def fake_ensure_workspace_exists(workspace_id: str) -> None:
        assert workspace_id == "ws_demo"

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: FakeObjectRelationStore(),
    )

    response = await object_runtime_module.project_object_graph(
        workspace_id="ws_demo",
        request=ObjectGraphProjectRequest(objects=[output_ref]),
    )

    projection = response.projections[0]
    assert projection.node_kind == "generated_reels_asset"
    assert projection.metadata["projection_source"] == "object_relation_registry"
    assert projection.relations[0].relation_kind == "generated_from_source"
    assert projection.relations[0].direction == "inbound"
    assert projection.relations[0].target_ref.object_kind == "reference"
