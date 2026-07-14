import importlib
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services import capability_runtime_activation
from app.services import capability_registry
from app.services.capability_api_loader import activate_capability_api_code
from app.services.capability_api_loader import seed_capability_api_descriptors


def test_capability_registry_compatibility_imports_share_one_module() -> None:
    backend_registry = importlib.import_module(
        "backend.app.services.capability_registry"
    )

    assert backend_registry is capability_registry
    assert backend_registry.get_registry() is capability_registry.get_registry()


class FakeActivationService:
    def record_activation_succeeded(self, **kwargs):
        return None

    def record_activation_failed(self, **kwargs):
        return None


def _write_reloadable_capability(base_dir: Path, *, label: str) -> None:
    capability_dir = base_dir / "sample_capability"
    api_dir = capability_dir / "api"
    services_dir = capability_dir / "services"
    api_dir.mkdir(parents=True, exist_ok=True)
    services_dir.mkdir(parents=True, exist_ok=True)

    (capability_dir / "__init__.py").write_text("", encoding="utf-8")
    (api_dir / "__init__.py").write_text("", encoding="utf-8")
    (services_dir / "__init__.py").write_text("", encoding="utf-8")

    (capability_dir / "manifest.yaml").write_text(
        """
code: sample_capability
apis:
  - code: sample_api
    path: api/routes.py
    enabled_by_default: true
    router_export: router
    prefix: /lazy
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (api_dir / "routes.py").write_text(
        """
from fastapi import APIRouter

from sample_capability.services.logic import get_payload

router = APIRouter(prefix="/sample")


@router.get("/ping")
def ping():
    return get_payload()
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (services_dir / "logic.py").write_text(
        f"""
def get_payload():
    return {{"label": "{label}"}}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_explicit_runtime_activation_refreshes_cached_capability_modules(
    tmp_path,
    monkeypatch,
):
    _write_reloadable_capability(tmp_path, label="old")
    monkeypatch.setenv("CAPABILITY_API_ACTIVATION_POLICY", "seed_only")
    monkeypatch.setattr(
        capability_runtime_activation,
        "PackActivationService",
        lambda: FakeActivationService(),
    )

    app = FastAPI()
    seed_capability_api_descriptors(
        app=app,
        remote_capabilities_dir=tmp_path,
        enable_all=True,
    )

    routers = activate_capability_api_code(
        app=app,
        capability_code="sample_capability",
        activation_service=FakeActivationService(),
    )

    assert len(routers) == 1
    client = TestClient(app)
    assert client.get("/lazy/sample/ping").json() == {"label": "old"}

    _write_reloadable_capability(tmp_path, label="new_runtime_value")

    result = capability_runtime_activation.activate_installed_capability_routes(
        app=app,
        capability_code="sample_capability",
        reason="test_refresh",
    )

    assert result["state"] == "activated"
    assert result["routes_removed"] >= 1
    assert result["modules_purged"] >= 1
    assert result["routers_registered"] == 1
    refreshed_client = TestClient(app)
    assert refreshed_client.get("/lazy/sample/ping").json() == {
        "label": "new_runtime_value"
    }


def test_targeted_capability_reload_preserves_other_registry_slices(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        capability_registry.PackActivationService,
        "record_activation_succeeded",
        lambda self, **kwargs: None,
    )

    def write_manifest(code: str, tool_name: str) -> None:
        capability_dir = tmp_path / code
        capability_dir.mkdir(parents=True, exist_ok=True)
        (capability_dir / "manifest.yaml").write_text(
            (
                f"code: {code}\n"
                "tools:\n"
                f"  - name: {tool_name}\n"
                f"    backend: capabilities.{code}.tools:{tool_name}\n"
            ),
            encoding="utf-8",
        )

    registry_capabilities = dict(capability_registry._registry.capabilities)
    registry_tools = dict(capability_registry._registry.tools)
    public_capabilities = dict(capability_registry.CAPABILITY_REGISTRY)
    public_tools = dict(capability_registry.TOOL_REGISTRY)
    try:
        write_manifest("pack_a", "tool_a_v1")
        write_manifest("pack_b", "tool_b")
        capability_registry.load_capabilities(tmp_path, reset=True)

        pack_b_before = capability_registry.CAPABILITY_REGISTRY["pack_b"]
        tool_b_before = capability_registry.TOOL_REGISTRY["pack_b.tool_b"]
        write_manifest("pack_a", "tool_a_v2")

        assert capability_registry.reload_capability("pack_a", tmp_path) is True
        assert "pack_a.tool_a_v1" not in capability_registry.TOOL_REGISTRY
        assert "pack_a.tool_a_v2" in capability_registry.TOOL_REGISTRY
        assert capability_registry.CAPABILITY_REGISTRY["pack_b"] is pack_b_before
        assert capability_registry.TOOL_REGISTRY["pack_b.tool_b"] is tool_b_before
    finally:
        capability_registry._registry.capabilities.clear()
        capability_registry._registry.capabilities.update(registry_capabilities)
        capability_registry._registry.tools.clear()
        capability_registry._registry.tools.update(registry_tools)
        capability_registry.CAPABILITY_REGISTRY.clear()
        capability_registry.CAPABILITY_REGISTRY.update(public_capabilities)
        capability_registry.TOOL_REGISTRY.clear()
        capability_registry.TOOL_REGISTRY.update(public_tools)
