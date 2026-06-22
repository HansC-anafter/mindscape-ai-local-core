import sys
import threading
import types

import pytest

from backend.app.services.object_index_sync_service import _invoke_backend_callable
from backend.app.models.object_runtime import ObjectInstanceSyncRequest
from backend.app.services.object_index_sync_service import (
    ObjectIndexSyncService,
    ObjectIndexSyncStatusTracker,
)


@pytest.mark.asyncio
async def test_invoke_backend_callable_runs_sync_backend_off_event_loop_thread():
    module_name = "backend.tests._fake_object_index_sync_backend"
    fake_module = types.ModuleType(module_name)
    loop_thread_id = threading.get_ident()

    def sync_indexer(workspace_id: str, ignored: str = "default"):
        return {
            "workspace_id": workspace_id,
            "ignored": ignored,
            "thread_id": threading.get_ident(),
        }

    fake_module.sync_indexer = sync_indexer
    sys.modules[module_name] = fake_module

    result = await _invoke_backend_callable(
        f"{module_name}:sync_indexer",
        workspace_id="ws_demo",
        ignored="included",
        extra="dropped",
    )

    assert result["workspace_id"] == "ws_demo"
    assert result["ignored"] == "included"
    assert result["thread_id"] != loop_thread_id


@pytest.mark.asyncio
async def test_invoke_backend_callable_runs_async_backend_off_event_loop_thread():
    module_name = "backend.tests._fake_object_index_sync_async_backend"
    fake_module = types.ModuleType(module_name)
    loop_thread_id = threading.get_ident()

    async def async_indexer(workspace_id: str):
        return {"workspace_id": workspace_id, "thread_id": threading.get_ident()}

    fake_module.async_indexer = async_indexer
    sys.modules[module_name] = fake_module

    result = await _invoke_backend_callable(
        f"{module_name}:async_indexer",
        workspace_id="ws_demo",
        extra="dropped",
    )

    assert result["workspace_id"] == "ws_demo"
    assert result["thread_id"] != loop_thread_id


@pytest.mark.asyncio
async def test_invoke_backend_callable_reloads_loaded_module_when_attr_is_missing(
    monkeypatch,
):
    module_name = "backend.tests._fake_object_index_sync_reloaded_backend"
    fake_module = types.ModuleType(module_name)
    reload_calls = []

    def reload_module(module):
        reload_calls.append(module.__name__)

        def sync_indexer(workspace_id: str):
            return {"workspace_id": workspace_id, "reloaded": True}

        module.sync_indexer = sync_indexer
        return module

    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setattr(
        "backend.app.services.object_index_sync_service.importlib.reload",
        reload_module,
    )

    result = await _invoke_backend_callable(
        f"{module_name}:sync_indexer",
        workspace_id="ws_demo",
    )

    assert reload_calls == [module_name]
    assert result == {"workspace_id": "ws_demo", "reloaded": True}


@pytest.mark.asyncio
async def test_sync_workspace_runs_catalog_and_store_work_off_event_loop_thread():
    module_name = "backend.tests._fake_object_index_sync_records_backend"
    fake_module = types.ModuleType(module_name)
    loop_thread_id = threading.get_ident()

    def sync_indexer(workspace_id: str, owner_pack: str, object_kind: str, **kwargs):
        return {
            "records": [
                {
                    "ref": {
                        "uri": f"mindscape://{owner_pack}/{object_kind}/object-1",
                        "owner_pack": owner_pack,
                        "object_kind": object_kind,
                        "object_id": "object-1",
                        "workspace_id": workspace_id,
                    },
                    "title": "Object 1",
                }
            ]
        }

    fake_module.sync_indexer = sync_indexer
    sys.modules[module_name] = fake_module

    class FakeCatalog:
        thread_id = None

        def list_entries(self, *, owner_pack=None, object_kind=None):
            self.thread_id = threading.get_ident()
            return [
                {
                    "owner_pack": "pack",
                    "object_kind": "kind",
                    "indexer_backend": f"{module_name}:sync_indexer",
                }
            ]

    class FakeInstanceStore:
        thread_id = None
        received_workspace_id = None
        received_records = []

        def upsert_many(self, workspace_id, records):
            self.thread_id = threading.get_ident()
            self.received_workspace_id = workspace_id
            self.received_records = list(records)
            return len(records)

    catalog = FakeCatalog()
    instance_store = FakeInstanceStore()
    service = ObjectIndexSyncService(
        catalog=catalog,
        instance_store=instance_store,
        workspace_store=object(),
        status_tracker=ObjectIndexSyncStatusTracker(),
    )

    response = await service.sync_workspace("workspace-1", ObjectInstanceSyncRequest())

    assert response.indexed_count == 1
    assert catalog.thread_id != loop_thread_id
    assert instance_store.thread_id != loop_thread_id
    assert instance_store.received_workspace_id == "workspace-1"
    assert [record.ref.object_id for record in instance_store.received_records] == [
        "object-1"
    ]


@pytest.mark.asyncio
async def test_sync_workspace_passes_exact_object_ids_to_indexer():
    module_name = "backend.tests._fake_object_index_sync_exact_backend"
    fake_module = types.ModuleType(module_name)
    captured_kwargs = {}

    def sync_indexer(workspace_id: str, owner_pack: str, object_kind: str, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "records": [
                {
                    "ref": {
                        "uri": f"mindscape://{owner_pack}/{object_kind}/object-2",
                        "owner_pack": owner_pack,
                        "object_kind": object_kind,
                        "object_id": "object-2",
                        "workspace_id": workspace_id,
                    },
                    "title": "Object 2",
                }
            ]
        }

    fake_module.sync_indexer = sync_indexer
    sys.modules[module_name] = fake_module

    class FakeCatalog:
        def list_entries(self, *, owner_pack=None, object_kind=None):
            return [
                {
                    "owner_pack": "pack",
                    "object_kind": "kind",
                    "indexer_backend": f"{module_name}:sync_indexer",
                }
            ]

    class FakeInstanceStore:
        received_records = []

        def upsert_many(self, workspace_id, records):
            self.received_records = list(records)
            return len(records)

    service = ObjectIndexSyncService(
        catalog=FakeCatalog(),
        instance_store=FakeInstanceStore(),
        workspace_store=object(),
        status_tracker=ObjectIndexSyncStatusTracker(),
    )

    response = await service.sync_workspace(
        "workspace-1",
        ObjectInstanceSyncRequest(object_ids=["object-2"], reason="exact-preview"),
    )

    assert response.indexed_count == 1
    assert captured_kwargs["object_ids"] == ["object-2"]
    assert captured_kwargs["reason"] == "exact-preview"
    assert [record.ref.object_id for record in service.instance_store.received_records] == [
        "object-2"
    ]
