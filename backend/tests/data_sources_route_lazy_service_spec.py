import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_probe(source: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}:{REPO_ROOT / 'backend'}"
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_data_sources_route_import_does_not_eager_load_service_store_chain():
    data = _run_probe(
        """
import json
import sys
import backend.app.routes.core.data_sources as data_sources_route

print(json.dumps({
    "prefix": data_sources_route.router.prefix,
    "data_source_service_loaded": "backend.app.services.data_source_service" in sys.modules,
    "tool_connection_store_loaded": "backend.app.services.tool_connection_store" in sys.modules,
}))
"""
    )

    assert data == {
        "prefix": "/api/v1/data-sources",
        "data_source_service_loaded": False,
        "tool_connection_store_loaded": False,
    }


def test_data_sources_service_factory_still_constructs_on_demand():
    data = _run_probe(
        """
import json
import sys
import types
import backend.app.routes.core.data_sources as data_sources_route

class FakeDataSourceService:
    pass

service_module = types.ModuleType("backend.app.services.data_source_service")
service_module.DataSourceService = FakeDataSourceService
sys.modules["backend.app.services.data_source_service"] = service_module

service = data_sources_route.get_data_source_service()
print(json.dumps({
    "service_type": type(service).__name__,
    "data_source_service_loaded": "backend.app.services.data_source_service" in sys.modules,
}))
"""
    )

    assert data == {
        "service_type": "FakeDataSourceService",
        "data_source_service_loaded": True,
    }
