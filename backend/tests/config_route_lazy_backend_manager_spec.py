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


def test_config_route_import_does_not_eager_create_backend_manager():
    data = _run_probe(
        """
import json
import sys
import backend.app.routes.core.config as config_route

print(json.dumps({
    "has_router": config_route.router.prefix,
    "backend_manager_loaded": "backend.app.services.backend_manager" in sys.modules,
    "agent_runner_loaded": "backend.app.services.agent_runner" in sys.modules,
    "llm_manager_loaded": "backend.app.services.llm_providers.manager" in sys.modules,
}))
"""
    )

    assert data == {
        "has_router": "/api/v1/config",
        "backend_manager_loaded": False,
        "agent_runner_loaded": False,
        "llm_manager_loaded": False,
    }


def test_config_route_lazy_backend_manager_still_constructs_on_demand():
    data = _run_probe(
        """
import json
import sys
import types
import backend.app.routes.core.config as config_route

class FakeConfigStore:
    pass

class FakeBackendManager:
    def __init__(self, config_store):
        self.config_store = config_store

config_store_module = types.ModuleType("backend.app.services.config_store")
config_store_module.ConfigStore = FakeConfigStore
backend_manager_module = types.ModuleType("backend.app.services.backend_manager")
backend_manager_module.BackendManager = FakeBackendManager
sys.modules["backend.app.services.config_store"] = config_store_module
sys.modules["backend.app.services.backend_manager"] = backend_manager_module

manager = config_route._get_backend_manager()
print(json.dumps({
    "manager_type": type(manager).__name__,
    "config_store_type": type(manager.config_store).__name__,
    "backend_manager_loaded": "backend.app.services.backend_manager" in sys.modules,
}))
"""
    )

    assert data == {
        "manager_type": "FakeBackendManager",
        "config_store_type": "FakeConfigStore",
        "backend_manager_loaded": True,
    }
