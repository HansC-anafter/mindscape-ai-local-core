import base64
import asyncio
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
    _default_backend_api_url,
)


def _fake_jwt(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    return f"header.{encoded}.signature"


def test_host_ws_client_builds_codex_host_session_registration_payload(monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-session-a")
    monkeypatch.setenv("HOME", "/Users/tester")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/Users/tester/.config")
    monkeypatch.setenv("MINDSCAPE_CODEX_POOL_GROUP", "codex-cli-pool")
    monkeypatch.setenv("MINDSCAPE_CODEX_POOL_PRIORITY", "2")
    monkeypatch.setenv("MINDSCAPE_OWNER_USER_ID", "default-user")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    payload = client._build_host_session_runtime_registration_payload()

    assert payload["workspace_id"] == "ws-1"
    assert payload["surface"] == "codex_cli"
    assert payload["client_id"] == "client-1"
    assert payload["owner_user_id"] == "default-user"
    assert payload["pool_group"] == "codex-cli-pool"
    assert payload["pool_priority"] == 2
    assert payload["metadata"]["CODEX_HOME"] == "/tmp/codex-session-a"
    assert payload["metadata"]["HOME"] == "/Users/tester"


def test_host_ws_client_uses_stable_default_client_id():
    client_a = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        task_handler=lambda _: None,
    )
    client_b = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        task_handler=lambda _: None,
    )
    client_c = HostBridgeWSClient(
        workspace_id="ws-2",
        host="localhost:8200",
        surface="codex_cli",
        task_handler=lambda _: None,
    )

    assert client_a.client_id == client_b.client_id
    assert client_a.client_id.startswith("codex_cli-ws-1-")
    assert client_c.client_id != client_a.client_id


def test_default_backend_api_url_prefers_control_plane_port(monkeypatch):
    monkeypatch.delenv("MINDSCAPE_BACKEND_API_URL", raising=False)
    monkeypatch.delenv("MINDSCAPE_CONTROL_PLANE_HOST", raising=False)
    monkeypatch.delenv("MINDSCAPE_CONTROL_PLANE_HOST_PORT", raising=False)

    assert _default_backend_api_url("localhost:8200") == "http://localhost:8220"


def test_host_ws_client_backend_api_url_defaults_to_control_plane(monkeypatch):
    monkeypatch.delenv("MINDSCAPE_BACKEND_API_URL", raising=False)
    monkeypatch.delenv("MINDSCAPE_CONTROL_PLANE_HOST", raising=False)
    monkeypatch.setenv("MINDSCAPE_CONTROL_PLANE_HOST_PORT", "8220")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    assert client.backend_api_url == "http://localhost:8220"


def test_host_ws_client_backend_request_sync_tries_backend_api_candidates(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8220")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    seen_urls = []

    class _FakeResponse:
        def __init__(self, body: str):
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        del timeout
        seen_urls.append(req.full_url)
        if req.full_url.startswith("http://localhost:8220"):
            raise urllib.error.URLError("timed out")
        return _FakeResponse('{"ok":true}')

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    backend_url, body = client._backend_request_sync(
        lambda backend_url: urllib.request.Request(f"{backend_url}/health", method="GET"),
        timeout=1.0,
    )

    assert seen_urls[0] == "http://localhost:8220/health"
    assert seen_urls[1] == "http://127.0.0.1:8220/health"
    assert backend_url == "http://127.0.0.1:8220"
    assert body == '{"ok":true}'


def test_host_ws_client_infers_default_codex_home(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    codex_home = home_dir / ".codex"
    codex_home.mkdir(parents=True)

    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    payload = client._build_host_session_runtime_registration_payload()

    assert payload["metadata"]["CODEX_HOME"] == str(codex_home)


def test_host_ws_client_builds_codex_home_pool_payloads(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_a = home_dir / ".codex-a"
    codex_b = home_dir / ".codex-b"
    codex_a.mkdir()
    codex_b.mkdir()

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_a))
    monkeypatch.setenv(
        "MINDSCAPE_CODEX_HOME_POOL",
        f"{codex_a}{os.pathsep}{codex_b}",
    )

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    payloads = client._build_host_session_runtime_registration_payloads()

    assert len(payloads) == 2
    assert payloads[0]["metadata"]["CODEX_HOME"] == str(codex_a)
    assert payloads[0]["pool_priority"] == 0
    assert payloads[1]["metadata"]["CODEX_HOME"] == str(codex_b)
    assert payloads[1]["pool_priority"] == 1


def test_host_ws_client_auto_discovers_logged_codex_homes(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_a = home_dir / ".codex-a"
    codex_b = home_dir / ".codex-b"
    codex_a.mkdir()
    codex_b.mkdir()
    (codex_a / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "a"}}),
        encoding="utf-8",
    )
    (codex_b / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "b"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    entries = client._codex_home_pool_entries()

    assert str(codex_a) in entries
    assert str(codex_b) in entries
    registry = json.loads(client._codex_seed_registry_path.read_text(encoding="utf-8"))
    assert sorted(item["path"] for item in registry["homes"]) == sorted(
        [str(codex_a), str(codex_b)]
    )


def test_host_ws_client_persists_primary_codex_home_as_seed(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = tmp_path / "custom-codex-home"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "x"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    payloads = client._build_host_session_runtime_registration_payloads()

    assert payloads[0]["metadata"]["CODEX_HOME"] == str(codex_primary)
    registry = json.loads(client._codex_seed_registry_path.read_text(encoding="utf-8"))
    assert any(item["path"] == str(codex_primary) for item in registry["homes"])


def test_host_ws_client_materializes_managed_codex_home_mirrors(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "seed"}}),
        encoding="utf-8",
    )
    (codex_primary / "config.toml").write_text("model = 'gpt-5.4'\n", encoding="utf-8")
    rules_dir = codex_primary / "rules"
    rules_dir.mkdir()
    (rules_dir / "default.rules").write_text("allow = true\n", encoding="utf-8")

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "3")
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    payloads = client._build_host_session_runtime_registration_payloads()
    codex_homes = [payload["metadata"]["CODEX_HOME"] for payload in payloads]

    assert len(codex_homes) == 3
    assert codex_homes[0] == str(codex_primary)
    primary_scope = payloads[0]["metadata"]["quota_scope_key"]
    assert payloads[0]["metadata"]["quota_scope_home"] == str(codex_primary)
    mirror_homes = codex_homes[1:]
    assert all(path.startswith(str(managed_root)) for path in mirror_homes)
    for payload, mirror_home in zip(payloads[1:], mirror_homes, strict=False):
        assert (Path(mirror_home) / "auth.json").is_file()
        assert (Path(mirror_home) / "config.toml").is_file()
        assert (Path(mirror_home) / "rules" / "default.rules").is_file()
        assert payload["metadata"]["quota_scope_key"] == primary_scope
        assert payload["metadata"]["quota_scope_home"] == str(codex_primary)
        assert payload["metadata"]["managed_seed_source_home"] == str(codex_primary)


@pytest.mark.asyncio
async def test_heartbeat_loop_closes_ws_when_send_raises(monkeypatch):
    class _BrokenWS:
        def __init__(self):
            self.closed = False

        async def send(self, _payload):
            raise RuntimeError("boom")

        async def close(self):
            self.closed = True

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    client.HEARTBEAT_INTERVAL = 0
    client._ws = _BrokenWS()

    async def _stop_after_first_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _stop_after_first_sleep)

    await client._heartbeat_loop()

    assert client._ws.closed is True


@pytest.mark.asyncio
async def test_connect_and_listen_recreates_pong_event_per_connection(monkeypatch):
    stale_event = asyncio.Event()

    class _FakeWS:
        def __init__(self):
            self._delivered = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._delivered:
                raise StopAsyncIteration
            self._delivered = True
            assert client._pong_received is not stale_event
            return json.dumps({"type": "pong"})

    class _FakeConnect:
        def __init__(self):
            self.ws = _FakeWS()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    client._pong_received = stale_event

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.host_ws_client.websockets.connect",
        lambda *args, **kwargs: _FakeConnect(),
    )

    await client._connect_and_listen()

    assert client._pong_received is None


def test_host_ws_client_duplicate_account_snapshot_does_not_reduce_mirror_capacity(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"account_id": "acct-a", "access_token": "seed-a"},
            }
        ),
        encoding="utf-8",
    )

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "3")
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    first_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    first_client._build_host_session_runtime_registration_payloads()

    second_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    payloads = second_client._build_host_session_runtime_registration_payloads()

    codex_homes = [payload["metadata"]["CODEX_HOME"] for payload in payloads]
    assert len(codex_homes) == 3
    assert codex_homes[0] == str(codex_primary)
    assert sum(path.startswith(str(managed_root)) for path in codex_homes[1:]) == 2


def test_host_ws_client_managed_mirror_registry_persists_generated_homes(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "seed"}}),
        encoding="utf-8",
    )

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "2")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    client._build_host_session_runtime_registration_payloads()

    registry = json.loads(client._codex_seed_registry_path.read_text(encoding="utf-8"))
    paths = sorted(item["path"] for item in registry["homes"])
    assert str(codex_primary) in paths
    assert any(path.startswith(str(managed_root)) for path in paths)


def test_host_ws_client_persists_current_account_snapshot_without_activating_duplicate(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"account_id": "acct-a", "access_token": "seed-a"},
            }
        ),
        encoding="utf-8",
    )

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "1")
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    payloads = client._build_host_session_runtime_registration_payloads()

    assert [payload["metadata"]["CODEX_HOME"] for payload in payloads] == [str(codex_primary)]
    registry = json.loads(client._codex_seed_registry_path.read_text(encoding="utf-8"))
    snapshot_paths = [
        item["path"]
        for item in registry["homes"]
        if item["path"].startswith(str(managed_root / "accounts"))
    ]
    assert len(snapshot_paths) == 1


def test_host_ws_client_preserves_prior_account_as_distinct_pool_seed(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "1")
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    def _write_auth(account_id: str, access_token: str) -> None:
        (codex_primary / "auth.json").write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {
                        "account_id": account_id,
                        "access_token": access_token,
                    },
                }
            ),
            encoding="utf-8",
        )

    _write_auth("acct-a", "seed-a")
    first_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    first_client._build_host_session_runtime_registration_payloads()

    _write_auth("acct-b", "seed-b")
    second_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    payloads = second_client._build_host_session_runtime_registration_payloads()

    payload_by_home = {
        payload["metadata"]["CODEX_HOME"]: payload
        for payload in payloads
    }
    assert str(codex_primary) in payload_by_home
    historical_homes = [
        home
        for home in payload_by_home.keys()
        if home != str(codex_primary)
    ]
    assert len(historical_homes) == 1
    historical_payload = payload_by_home[historical_homes[0]]
    primary_payload = payload_by_home[str(codex_primary)]
    assert historical_payload["metadata"]["account_key"] != primary_payload["metadata"]["account_key"]
    assert historical_payload["metadata"]["quota_scope_key"] != primary_payload["metadata"]["quota_scope_key"]


def test_host_ws_client_distinguishes_login_principals_sharing_account_id(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "1")
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    def _write_auth(*, account_id: str, chatgpt_user_id: str, email: str) -> None:
        (codex_primary / "auth.json").write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {
                        "account_id": account_id,
                        "access_token": f"access-{chatgpt_user_id}",
                        "id_token": _fake_jwt(
                            {
                                "email": email,
                                "sub": f"google-oauth2|{chatgpt_user_id}",
                                "https://api.openai.com/auth": {
                                    "chatgpt_user_id": chatgpt_user_id,
                                    "chatgpt_account_id": account_id,
                                },
                            }
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )

    shared_account_id = "shared-team-account"
    _write_auth(
        account_id=shared_account_id,
        chatgpt_user_id="user-a",
        email="first@example.com",
    )
    first_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    first_client._build_host_session_runtime_registration_payloads()

    _write_auth(
        account_id=shared_account_id,
        chatgpt_user_id="user-b",
        email="second@example.com",
    )
    second_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    payloads = second_client._build_host_session_runtime_registration_payloads()

    payload_by_home = {
        payload["metadata"]["CODEX_HOME"]: payload
        for payload in payloads
    }
    assert str(codex_primary) in payload_by_home
    historical_homes = [
        home
        for home in payload_by_home.keys()
        if home != str(codex_primary)
    ]
    assert len(historical_homes) == 1
    historical_payload = payload_by_home[historical_homes[0]]
    primary_payload = payload_by_home[str(codex_primary)]
    assert historical_payload["metadata"]["account_key"] != primary_payload["metadata"]["account_key"]
    assert historical_payload["metadata"]["quota_scope_key"] != primary_payload["metadata"]["quota_scope_key"]


def test_host_ws_client_refresh_codex_home_seeds_reports_distinct_accounts(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()

    managed_root = tmp_path / "managed-codex-pool"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_SIZE", "1")

    (codex_primary / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "shared-team-account",
                    "access_token": "seed-a",
                    "id_token": _fake_jwt(
                        {
                            "email": "first@example.com",
                            "sub": "google-oauth2|user-a",
                            "https://api.openai.com/auth": {
                                "chatgpt_user_id": "user-a",
                                "chatgpt_account_id": "shared-team-account",
                            },
                        }
                    ),
                },
            }
        ),
        encoding="utf-8",
    )

    first_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    first_client.refresh_codex_home_seeds()

    (codex_primary / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "shared-team-account",
                    "access_token": "seed-b",
                    "id_token": _fake_jwt(
                        {
                            "email": "second@example.com",
                            "sub": "google-oauth2|user-b",
                            "https://api.openai.com/auth": {
                                "chatgpt_user_id": "user-b",
                                "chatgpt_account_id": "shared-team-account",
                            },
                        }
                    ),
                },
            }
        ),
        encoding="utf-8",
    )

    second_client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    summary = second_client.refresh_codex_home_seeds()

    assert summary["refreshed"] is True
    assert summary["real_home_count"] == 1
    assert summary["account_snapshot_count"] == 2
    assert summary["distinct_account_count"] == 2


@pytest.mark.asyncio
async def test_host_ws_client_skips_duplicate_registration_when_payload_unchanged(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "seed"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    calls: list[list[dict[str, object]]] = []

    def _fake_register(payloads=None):
        calls.append(payloads or [])
        return {"registered": True, "runtime_id": "runtime-codex-1"}

    monkeypatch.setattr(client, "_register_host_session_runtime_sync", _fake_register)

    await client._maybe_register_host_session_runtime()
    await client._maybe_register_host_session_runtime()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_host_ws_client_unknown_execution_error_triggers_rest_recovery(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    execution_id = "11111111-2222-3333-4444-555555555555"
    result_message = {
        "type": "result",
        "execution_id": execution_id,
        "status": "completed",
        "output": "ok",
    }
    client._remember_result(execution_id, result_message)
    waiter = asyncio.get_running_loop().create_future()
    client._result_ack_waiters[execution_id] = waiter

    recovered: list[str] = []

    async def _fake_submit(message, *, queue_on_failure=True):
        recovered.append(message["execution_id"])
        return True

    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    await client._handle_message(
        {"type": "error", "error": f"Unknown execution {execution_id}"}
    )
    await asyncio.sleep(0)

    assert recovered == [execution_id]
    assert execution_id not in client._result_ack_waiters


def test_host_ws_client_switches_to_polling_after_repeated_403(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    class _Forbidden(Exception):
        status_code = 403

    assert client._should_fallback_to_polling(_Forbidden()) is False
    assert client._should_fallback_to_polling(_Forbidden()) is False
    assert client._should_fallback_to_polling(_Forbidden()) is True


def test_host_ws_client_treats_transport_denial_errors_as_polling_candidates(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    error = RuntimeError("did not receive a valid HTTP response")

    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is True


def test_host_ws_client_treats_ws_open_timeout_as_polling_candidate(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    error = RuntimeError("timed out during opening handshake")

    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is True


def test_host_ws_client_polling_reserve_backoff_grows_and_caps(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    delays = [
        client._polling_reserve_failure_delay(attempt)
        for attempt in range(1, 8)
    ]

    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


@pytest.mark.asyncio
async def test_host_ws_client_handles_polled_dispatch_via_rest(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    async def _fake_task_handler(message):
        assert message["execution_id"] == "exec-1"
        return {
            "status": "completed",
            "output": "ok",
            "files_created": ["persona_operating_system.md"],
            "metadata": {"runtime_id": "runtime-codex-1"},
        }

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=_fake_task_handler,
    )

    acknowledged: list[tuple[str, str]] = []
    submitted: list[dict[str, object]] = []

    def _fake_ack(execution_id: str, lease_id: str):
        acknowledged.append((execution_id, lease_id))
        return {"acknowledged": True}

    async def _fake_submit(message, *, queue_on_failure=True):
        submitted.append(message)
        return True

    monkeypatch.setattr(client, "_ack_reserved_task_via_rest_sync", _fake_ack)
    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    await client._handle_polled_dispatch(
        {
            "execution_id": "exec-1",
            "lease_id": "lease-1",
            "task": "Create deliverable",
        }
    )

    assert acknowledged == [("exec-1", "lease-1")]
    assert submitted[0]["execution_id"] == "exec-1"
    assert submitted[0]["lease_id"] == "lease-1"
    assert submitted[0]["metadata"]["transport"] == "polling"


@pytest.mark.asyncio
async def test_host_ws_client_acks_queued_ws_dispatches_without_blocking_receive_loop(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "host-ws-client-spool.json"),
    )

    allow_first_finish = asyncio.Event()
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    completed: list[str] = []
    sent_messages: list[dict[str, object]] = []

    async def _fake_task_handler(message):
        execution_id = message["execution_id"]
        if execution_id == "exec-1":
            first_started.set()
            await allow_first_finish.wait()
        else:
            second_started.set()
        completed.append(execution_id)
        return {
            "status": "completed",
            "output": execution_id,
        }

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=_fake_task_handler,
    )

    async def _fake_send(message):
        sent_messages.append(message)

    async def _fake_deliver_result(execution_id, result_message):
        sent_messages.append(
            {
                "type": "result",
                "execution_id": execution_id,
                "status": result_message["status"],
            }
        )
        return "ws_push"

    monkeypatch.setattr(client, "_send", _fake_send)
    monkeypatch.setattr(client, "_deliver_result", _fake_deliver_result)

    await client._handle_dispatch({"execution_id": "exec-1", "task": "first"})
    await asyncio.wait_for(first_started.wait(), timeout=1)

    await client._handle_dispatch({"execution_id": "exec-2", "task": "second"})
    await asyncio.sleep(0)

    acked_ids = [
        message["execution_id"]
        for message in sent_messages
        if message.get("type") == "ack"
    ]
    assert acked_ids == ["exec-1", "exec-2"]
    assert not second_started.is_set()

    allow_first_finish.set()
    await asyncio.wait_for(second_started.wait(), timeout=1)

    for _ in range(20):
        if completed == ["exec-1", "exec-2"]:
            break
        await asyncio.sleep(0.01)

    assert completed == ["exec-1", "exec-2"]


def test_host_ws_client_dispatch_lock_binds_to_running_loop(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
    )

    assert client._dispatch_lock is None
    assert client._dispatch_lock_loop is None

    async def _bind_lock():
        lock = client._get_dispatch_lock()
        assert lock is client._get_dispatch_lock()
        assert client._dispatch_lock is lock
        assert client._dispatch_lock_loop is asyncio.get_running_loop()

    asyncio.run(_bind_lock())


def test_host_ws_client_rest_result_payload_includes_attachments(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://backend.test")

    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"accepted": True}).encode("utf-8")

    def _fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    response = client._submit_result_via_rest_sync(
        {
            "execution_id": "exec-1",
            "status": "completed",
            "output": "ok",
            "lease_id": "lease-1",
            "attachments": [
                {
                    "filename": "persona_operating_system.md",
                    "content": "# Persona\n",
                }
            ],
            "metadata": {
                "effective_sandbox_path": "/tmp/ws",
                "transport": "polling",
            },
        }
    )

    assert response["accepted"] is True
    assert captured["url"] == "http://backend.test/api/v1/mcp/agent/result"
    assert captured["payload"]["lease_id"] == "lease-1"
    assert captured["payload"]["attachments"] == [
        {
            "filename": "persona_operating_system.md",
            "content": "# Persona\n",
        }
    ]
    assert captured["payload"]["metadata"]["transport"] == "polling"
