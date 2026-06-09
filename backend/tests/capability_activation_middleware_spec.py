from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.app_bootstrap import capability_activation_middleware
from app.services import capability_api_loader
from app.services.capability_api_loader import (
    activate_capability_api_code,
    seed_capability_api_descriptors,
)


def _write_test_capability(base_dir: Path) -> None:
    capability_dir = base_dir / "sample_capability"
    api_dir = capability_dir / "api"
    api_dir.mkdir(parents=True)

    (capability_dir / "manifest.yaml").write_text(
        """
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

router = APIRouter(prefix="/sample")

@router.get("/ping")
def ping():
    return {"ok": True}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_future_annotation_capability(base_dir: Path) -> None:
    capability_dir = base_dir / "future_annotation_capability"
    api_dir = capability_dir / "api"
    api_dir.mkdir(parents=True)

    (capability_dir / "manifest.yaml").write_text(
        """
apis:
  - code: future_annotation_api
    path: api/routes.py
    enabled_by_default: true
    router_export: router
    prefix: /future
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (api_dir / "routes.py").write_text(
        """
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/sample")

class Payload(BaseModel):
    label: Optional[str] = None

@router.get("/item", response_model=Payload)
def item() -> Payload:
    return Payload(label="ok")
""".strip()
        + "\n",
        encoding="utf-8",
    )


class FakeActivationService:
    def record_activation_succeeded(self, **kwargs):
        return None

    def record_activation_failed(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_seed_only_request_activation_uses_thread_bridge(tmp_path, monkeypatch):
    _write_test_capability(tmp_path)
    monkeypatch.setenv("CAPABILITY_API_ACTIVATION_POLICY", "seed_only")

    app = FastAPI()
    app.state.capability_activation_service = FakeActivationService()
    seed_capability_api_descriptors(
        app=app,
        remote_capabilities_dir=tmp_path,
        enable_all=True,
    )

    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        capability_activation_middleware.asyncio,
        "to_thread",
        fake_to_thread,
    )
    request = SimpleNamespace(
        method="GET",
        app=app,
        url=SimpleNamespace(path="/lazy/sample/ping"),
    )

    response = await capability_activation_middleware.ensure_capability_activation_for_request(
        request
    )

    assert response is None
    assert len(calls) == 1
    assert calls[0][2]["capability_code"] == "sample_capability"


def test_activation_retries_when_descriptor_key_is_stale(tmp_path, monkeypatch):
    _write_test_capability(tmp_path)
    monkeypatch.setenv("CAPABILITY_API_ACTIVATION_POLICY", "seed_only")

    app = FastAPI()
    app.state.capability_activation_service = FakeActivationService()
    descriptors = seed_capability_api_descriptors(
        app=app,
        remote_capabilities_dir=tmp_path,
        enable_all=True,
    )
    state = capability_api_loader._get_runtime_state(app)
    state["registered_descriptor_keys"].add(
        capability_api_loader._descriptor_state_key(descriptors[0])
    )

    routers = activate_capability_api_code(
        app=app,
        capability_code="sample_capability",
        activation_service=FakeActivationService(),
    )

    assert len(routers) == 1
    assert TestClient(app).get("/lazy/sample/ping").json() == {"ok": True}


def test_activation_loads_future_annotation_response_models(tmp_path, monkeypatch):
    _write_future_annotation_capability(tmp_path)
    monkeypatch.setenv("CAPABILITY_API_ACTIVATION_POLICY", "seed_only")

    app = FastAPI()
    seed_capability_api_descriptors(
        app=app,
        remote_capabilities_dir=tmp_path,
        enable_all=True,
    )

    routers = activate_capability_api_code(
        app=app,
        capability_code="future_annotation_capability",
        activation_service=FakeActivationService(),
    )

    assert len(routers) == 1
    assert TestClient(app).get("/future/sample/item").json() == {"label": "ok"}
