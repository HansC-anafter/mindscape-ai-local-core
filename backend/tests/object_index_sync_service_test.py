import sys
import threading
import types

import pytest

from backend.app.services.object_index_sync_service import _invoke_backend_callable


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
