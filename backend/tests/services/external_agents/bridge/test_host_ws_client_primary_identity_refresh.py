import json

from backend.app.services.external_agents.bridge.host_ws_client import HostBridgeWSClient
from host_ws_client_test_support import _fake_jwt


def test_host_ws_client_does_not_snapshot_prior_primary_login(
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
    assert historical_homes == []
    primary_payload = payload_by_home[str(codex_primary)]
    assert primary_payload["metadata"]["auth_account_id"] == "acct-b"

def test_host_ws_client_replaces_primary_identity_without_snapshotting_prior_login(
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
    primary_payload = payload_by_home[str(codex_primary)]
    assert historical_homes == []
    assert primary_payload["metadata"]["login_email"] == "second@example.com"
    assert primary_payload["metadata"]["account_label"] == "second@example.com"

def test_host_ws_client_refresh_codex_home_seeds_does_not_snapshot_primary_accounts(
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
    assert summary["account_snapshot_count"] == 0
    assert summary["distinct_account_count"] == 1
