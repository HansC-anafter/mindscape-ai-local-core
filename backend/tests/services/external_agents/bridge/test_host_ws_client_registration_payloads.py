import json
import os
import urllib.error
import urllib.request

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
    _default_backend_api_url,
)
from host_ws_client_test_support import _fake_jwt


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

def test_host_ws_client_does_not_tombstone_primary_from_archived_auth(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    managed_root = tmp_path / "managed-codex-pool"
    archive_root = managed_root / "captured-primary-auth"
    archive_root.mkdir(parents=True)
    (archive_root / "acct-a-20260507T120603581026Z.auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    payloads = client._build_host_session_runtime_registration_payloads()

    assert len(payloads) == 1
    assert payloads[0]["metadata"]["CODEX_HOME"] == str(codex_primary)
    assert "codex_primary_auth_vacated" not in payloads[0]["metadata"]
    assert payloads[0]["pool_enabled"] is True

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

def test_host_ws_client_does_not_materialize_managed_codex_home_mirrors(monkeypatch, tmp_path):
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

    assert len(codex_homes) == 1
    assert codex_homes[0] == str(codex_primary)
    primary_scope = payloads[0]["metadata"]["quota_scope_key"]
    assert payloads[0]["metadata"]["quota_scope_home"] == str(codex_primary)
    assert payloads[0]["metadata"]["quota_scope_key"] == primary_scope
    assert not managed_root.exists()

def test_host_ws_client_does_not_materialize_duplicate_account_snapshot_capacity(
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
    assert codex_homes == [str(codex_primary)]
    account_homes = sorted((managed_root / "accounts").glob("acct-*"))
    assert account_homes == []

def test_host_ws_client_discovers_managed_account_homes_as_pool_capacity(
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
                "tokens": {
                    "account_id": "acct-primary",
                    "id_token": _fake_jwt(
                        {
                            "email": "primary@example.com",
                            "sub": "google-oauth2|primary",
                        }
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    managed_root = tmp_path / "managed-codex-pool"
    account_home = managed_root / "accounts" / "acct-a"
    account_home.mkdir(parents=True)
    (account_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "version": 1,
                "account_snapshot": True,
                "source_home": str(codex_primary),
                "updated_at": "2026-05-06T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (account_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "last_refresh": "2026-05-06T00:05:00+00:00",
                "tokens": {
                    "account_id": "acct-a",
                    "refresh_token": "refresh-a",
                    "id_token": _fake_jwt(
                        {
                            "email": "account-a@example.com",
                            "sub": "google-oauth2|account-a",
                        }
                    ),
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))
    monkeypatch.setenv("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", str(managed_root))
    monkeypatch.delenv("MINDSCAPE_CODEX_HOME_POOL", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    payloads = client._build_host_session_runtime_registration_payloads()

    by_home = {payload["metadata"]["CODEX_HOME"]: payload for payload in payloads}
    assert set(by_home) == {str(codex_primary), str(account_home)}
    assert by_home[str(account_home)]["metadata"]["codex_seed_kind"] == "account_snapshot"
    assert by_home[str(account_home)]["metadata"]["login_email"] == "account-a@example.com"
    assert "account_home_validated_at" not in by_home[str(account_home)]["metadata"]
    assert (
        by_home[str(account_home)]["metadata"]["codex_auth_has_runtime_credentials"]
        is True
    )
