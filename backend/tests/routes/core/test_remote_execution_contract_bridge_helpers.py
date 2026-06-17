import ast
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

_repo_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

_cloud_root = os.path.abspath(os.path.join(_repo_root, "..", "mindscape-ai-cloud"))
if os.path.isdir(_cloud_root) and _cloud_root not in sys.path:
    sys.path.insert(0, _cloud_root)

_site_hub_root = os.path.abspath(os.path.join(_repo_root, "..", "site-hub"))
_site_hub_api_root = os.path.join(_site_hub_root, "site-hub-api")
_site_hub_common_root = os.path.join(_site_hub_root, "site-hub-common")
for _path in (_site_hub_api_root, _site_hub_common_root):
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

BRIDGE_SIBLINGS_AVAILABLE = os.path.isdir(_cloud_root) and os.path.isdir(
    _site_hub_root
)


def _load_module(module_name: str, relative_path: str):
    module_path = os.path.join(_repo_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_site_hub_execution_control(monkeypatch):
    module_path = Path(_site_hub_api_root) / "v1" / "execution_control.py"
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    start_request = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "StartExecutionRequest":
            start_request = node
            break
    assert start_request is not None, "StartExecutionRequest not found in site-hub execution_control.py"

    isolated_module = ast.Module(body=[start_request], type_ignores=[])
    namespace = {
        "BaseModel": BaseModel,
        "Field": Field,
        "Optional": Optional,
        "Dict": Dict,
        "Any": Any,
    }
    exec(compile(isolated_module, str(module_path), "exec"), namespace)
    return namespace["StartExecutionRequest"]


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeField:
    def __eq__(self, other):
        return ("eq", other)

    def __ne__(self, other):
        return ("ne", other)

    def is_(self, other):
        return ("is", other)

    def isnot(self, other):
        return ("isnot", other)

    def desc(self):
        return self


class _FakeRuntimeEnvironmentModel:
    id = _FakeField()
    supports_dispatch = _FakeField()
    config_url = _FakeField()
    auth_type = _FakeField()
    recommended_for_dispatch = _FakeField()
    is_default = _FakeField()
    updated_at = _FakeField()


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    def query(self, model):
        result = self._results.pop(0) if self._results else None
        return _FakeQuery(result)

    def close(self):
        return None


def _install_fake_runtime_modules(monkeypatch, results):
    fake_db_module = types.ModuleType("app.database")

    def _get_db_postgres():
        yield _FakeSession(results)

    fake_db_module.get_db_postgres = _get_db_postgres
    fake_runtime_module = types.ModuleType("app.models.runtime_environment")
    fake_runtime_module.RuntimeEnvironment = _FakeRuntimeEnvironmentModel

    monkeypatch.setitem(sys.modules, "app.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "app.models.runtime_environment", fake_runtime_module)
