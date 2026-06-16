from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.routes.runtime_dispatch import router
from backend.app.services.resource_governance import context as governance_context
from backend.app.services.runtime_dispatch.feature_gate import (
    get_runtime_dispatch_feature_gate,
    is_runtime_dispatch_enabled,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="default_user",
        tenant_id="local",
        workspace_ids=["ws-runtime"],
    )
    return TestClient(app)


def _limited_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="limited-user",
        tenant_id="local",
        workspace_ids=["ws-runtime"],
    )
    return TestClient(app)


def test_runtime_dispatch_gate_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("RUNTIME_DISPATCH_ENABLED", raising=False)

    assert is_runtime_dispatch_enabled() is False
    assert get_runtime_dispatch_feature_gate() == {
        "enabled": False,
        "env_var": "RUNTIME_DISPATCH_ENABLED",
        "default_enabled": False,
        "reason": "runtime_dispatch_disabled",
    }


def test_runtime_dispatch_gate_accepts_explicit_true(monkeypatch):
    monkeypatch.setenv("RUNTIME_DISPATCH_ENABLED", "true")

    assert is_runtime_dispatch_enabled() is True
    assert get_runtime_dispatch_feature_gate()["reason"] is None


def test_preview_apply_repair_reject_without_mutation_when_gate_disabled(monkeypatch):
    monkeypatch.delenv("RUNTIME_DISPATCH_ENABLED", raising=False)
    client = _client()

    for operation in ("preview", "apply", "repair"):
        response = client.post(
            f"/api/v1/runtime-dispatch/{operation}",
            json={"workspace_id": "ws-runtime"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["accepted"] is False
        assert payload["operation"] == operation
        assert payload["reason"] == "runtime_dispatch_disabled"
        assert payload["mutation_performed"] is False
        assert payload["db_mutation_performed"] is False
        assert payload["redis_mutation_performed"] is False
        assert payload["repair_required"] is False


def test_preview_still_requires_workspace_access_when_gate_disabled(monkeypatch):
    monkeypatch.delenv("RUNTIME_DISPATCH_ENABLED", raising=False)
    monkeypatch.setattr(governance_context, "get_default_user_id", lambda: "default_user")
    client = _limited_client()

    response = client.post(
        "/api/v1/runtime-dispatch/preview",
        json={"workspace_id": "other-workspace"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "workspace_resource_access_denied"
