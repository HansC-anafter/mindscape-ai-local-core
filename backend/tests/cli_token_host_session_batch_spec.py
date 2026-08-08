import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.routes.core import cli_token
from backend.app.routes.core.cli_token_core import host_session_api
from backend.app.routes.core.cli_token_core.schemas import (
    RegisterHostSessionRuntimeBatchRequest,
    RegisterHostSessionRuntimeRequest,
)


def _runtime_request(
    index: int,
    *,
    workspace_id: str = "ws-1",
    surface: str = "codex_cli",
    owner_user_id: str | None = "user-1",
) -> RegisterHostSessionRuntimeRequest:
    return RegisterHostSessionRuntimeRequest(
        workspace_id=workspace_id,
        surface=surface,
        owner_user_id=owner_user_id,
        client_id=f"client-{index}",
        runtime_id=f"runtime-{index}",
        metadata={"HOME": "/tmp/home", "CODEX_HOME": f"/tmp/codex-{index}"},
    )


def test_batch_contract_has_fixed_item_bounds() -> None:
    with pytest.raises(ValidationError):
        RegisterHostSessionRuntimeBatchRequest(runtimes=[])

    with pytest.raises(ValidationError):
        RegisterHostSessionRuntimeBatchRequest(
            runtimes=[_runtime_request(index) for index in range(257)]
        )

    accepted = RegisterHostSessionRuntimeBatchRequest(
        runtimes=[_runtime_request(index) for index in range(256)]
    )
    assert len(accepted.runtimes) == 256


def test_batch_resolves_owner_once_and_preserves_runtime_order(monkeypatch) -> None:
    owner_loads: list[str] = []
    registrations: list[tuple[str, str]] = []

    def _load_owner(workspace_id: str) -> str:
        owner_loads.append(workspace_id)
        return "user-1"

    def _register(*, owner_user_id, request):
        registrations.append((owner_user_id, request.runtime_id))
        return {"id": request.runtime_id, "metadata": dict(request.metadata)}

    monkeypatch.setattr(host_session_api, "_load_workspace_owner_user_id", _load_owner)
    monkeypatch.setattr(host_session_api, "_register_host_session_runtime", _register)

    request = RegisterHostSessionRuntimeBatchRequest(
        runtimes=[
            _runtime_request(index, owner_user_id=None) for index in range(40)
        ]
    )
    response = host_session_api._register_host_session_runtime_batch_request(request)

    assert owner_loads == ["ws-1"]
    assert registrations == [
        ("user-1", f"runtime-{index}") for index in range(40)
    ]
    assert response["runtime_id"] == "runtime-0"
    assert response["registered_runtime_ids"] == [
        f"runtime-{index}" for index in range(40)
    ]
    assert response["registered_runtime_count"] == 40


@pytest.mark.parametrize(
    "runtimes, expected_detail",
    [
        (
            [_runtime_request(0), _runtime_request(1, workspace_id="ws-2")],
            "one workspace",
        ),
        (
            [_runtime_request(0), _runtime_request(1, owner_user_id="user-2")],
            "one owner",
        ),
        (
            [_runtime_request(0), _runtime_request(1, surface="gemini_cli")],
            "not implemented",
        ),
    ],
)
def test_batch_rejects_mixed_scope_before_registration(
    monkeypatch,
    runtimes,
    expected_detail,
) -> None:
    registrations: list[str] = []
    monkeypatch.setattr(
        host_session_api,
        "_register_host_session_runtime",
        lambda **kwargs: registrations.append(kwargs["request"].runtime_id),
    )

    with pytest.raises(HTTPException) as exc_info:
        host_session_api._register_host_session_runtime_batch_request(
            RegisterHostSessionRuntimeBatchRequest(runtimes=runtimes)
        )

    assert exc_info.value.status_code == 400
    assert expected_detail in str(exc_info.value.detail)
    assert registrations == []


def test_batch_stops_at_first_registration_failure(monkeypatch) -> None:
    registrations: list[str] = []

    def _register(*, owner_user_id, request):
        registrations.append(request.runtime_id)
        if request.runtime_id == "runtime-2":
            raise RuntimeError("write failed")
        return {"id": request.runtime_id}

    monkeypatch.setattr(host_session_api, "_register_host_session_runtime", _register)
    request = RegisterHostSessionRuntimeBatchRequest(
        runtimes=[_runtime_request(index) for index in range(5)]
    )

    with pytest.raises(RuntimeError, match="write failed"):
        host_session_api._register_host_session_runtime_batch_request(request)

    assert registrations == ["runtime-0", "runtime-1", "runtime-2"]


def test_single_request_keeps_existing_response_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        host_session_api,
        "_register_host_session_runtime",
        lambda **kwargs: {
            "id": kwargs["request"].runtime_id,
            "metadata": dict(kwargs["request"].metadata),
        },
    )

    response = host_session_api._register_host_session_runtime_request(
        _runtime_request(7)
    )

    assert response == {
        "registered": True,
        "runtime_id": "runtime-7",
        "owner_user_id": "user-1",
        "runtime": {
            "id": "runtime-7",
            "metadata": {"HOME": "/tmp/home", "CODEX_HOME": "/tmp/codex-7"},
        },
    }


def test_plural_route_binds_batch_contract(monkeypatch) -> None:
    captured: list[RegisterHostSessionRuntimeBatchRequest] = []

    def _register(request: RegisterHostSessionRuntimeBatchRequest):
        captured.append(request)
        return {
            "registered": True,
            "runtime_id": "runtime-0",
            "registered_runtime_ids": ["runtime-0"],
            "registered_runtime_count": 1,
        }

    monkeypatch.setattr(
        cli_token,
        "_register_host_session_runtime_batch_request",
        _register,
    )
    app = FastAPI()
    app.include_router(cli_token.router)

    response = TestClient(app).post(
        "/api/v1/auth/cli-runtime/register-host-sessions",
        json={"runtimes": [_runtime_request(0).model_dump()]},
    )

    assert response.status_code == 200
    assert response.json()["registered_runtime_count"] == 1
    assert len(captured) == 1
    assert captured[0].runtimes[0].runtime_id == "runtime-0"
