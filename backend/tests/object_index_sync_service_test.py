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

        def upsert_many(self, workspace_id, records):
            self.thread_id = threading.get_ident()
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
