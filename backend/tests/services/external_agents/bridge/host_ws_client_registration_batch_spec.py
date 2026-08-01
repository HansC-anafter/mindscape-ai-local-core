import json

from backend.app.services.external_agents.bridge.host_ws_client import HostBridgeWSClient


def _client() -> HostBridgeWSClient:
    return HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )


def test_host_registration_sends_one_bounded_batch_request(monkeypatch) -> None:
    client = _client()
    payloads = [
        {
            "workspace_id": "ws-1",
            "surface": "codex_cli",
            "owner_user_id": "user-1",
            "runtime_id": f"runtime-{index}",
            "metadata": {"CODEX_HOME": f"/tmp/codex-{index}"},
        }
        for index in range(40)
    ]
    requests = []

    def _backend_request(build_request, *, timeout):
        request = build_request("http://control")
        requests.append((request, timeout))
        return (
            "http://control",
            json.dumps(
                {
                    "registered": True,
                    "runtime_id": "runtime-0",
                    "registered_runtime_ids": [
                        f"runtime-{index}" for index in range(40)
                    ],
                    "registered_runtime_count": 40,
                }
            ),
        )

    monkeypatch.setattr(client, "_backend_request_sync", _backend_request)

    response = client._register_host_session_runtime_sync(payloads)

    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == (
        "http://control/api/v1/auth/cli-runtime/register-host-sessions"
    )
    assert request.method == "POST"
    assert json.loads(request.data.decode("utf-8")) == {"runtimes": payloads}
    assert timeout == client.HOST_SESSION_REGISTER_TIMEOUT
    assert response["runtime_id"] == "runtime-0"
    assert response["registered_runtime_count"] == 40


def test_host_registration_skips_request_for_empty_inventory(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(
        client,
        "_backend_request_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("empty inventory must not call backend")
        ),
    )

    assert client._register_host_session_runtime_sync([]) == {}
