import json
import os

from backend.app.services.external_agents.bridge.host_ws_client import HostBridgeWSClient
from host_ws_client_test_support import _fake_jwt


def test_host_ws_client_does_not_carry_legacy_account_home_validated_stamp(
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
                    "refresh_token": "primary-refresh",
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
                "auth_synced_at": "2026-05-07T05:19:26+00:00",
                "account_home_validated_at": "2026-05-07T04:20:48+00:00",
            }
        ),
        encoding="utf-8",
    )
    (account_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
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

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    payloads = client._build_host_session_runtime_registration_payloads()
    by_home = {payload["metadata"]["CODEX_HOME"]: payload for payload in payloads}

    account_metadata = by_home[str(account_home)]["metadata"]
    assert account_metadata["codex_seed_kind"] == "account_snapshot"
    assert account_metadata["HOME"] == str(account_home)
    assert account_metadata["XDG_CONFIG_HOME"] == str(account_home / ".config")
    assert "account_home_validated_at" not in account_metadata
    assert account_metadata["seed_auth_synced_at"] == "2026-05-07T05:19:26+00:00"

def test_host_ws_client_does_not_sync_primary_auth_to_matching_account_home(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    primary_auth = {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-05-06T20:41:50+00:00",
        "tokens": {
            "account_id": "acct-a",
            "access_token": "fresh-access",
            "refresh_token": "fresh-refresh",
            "id_token": _fake_jwt(
                {
                    "email": "account-a@example.com",
                    "sub": "google-oauth2|account-a",
                    "https://api.openai.com/auth": {
                        "chatgpt_user_id": "user-a",
                        "chatgpt_account_id": "acct-a",
                    },
                }
            ),
        },
    }
    (codex_primary / "auth.json").write_text(
        json.dumps(primary_auth),
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
                "login_email": "account-a@example.com",
                "auth_account_id": "acct-a",
                "auth_chatgpt_user_id": "user-a",
            }
        ),
        encoding="utf-8",
    )
    (account_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "last_refresh": "2026-05-05T00:00:00+00:00",
                "tokens": {
                    "account_id": "acct-a",
                    "refresh_token": "stale-refresh",
                    "id_token": primary_auth["tokens"]["id_token"],
                },
            }
        ),
        encoding="utf-8",
    )
    os.utime(account_home / "auth.json", (1_778_100_000, 1_778_100_000))
    os.utime(codex_primary / "auth.json", (1_778_200_000, 1_778_200_000))

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

    account_auth = json.loads((account_home / "auth.json").read_text(encoding="utf-8"))
    account_seed = json.loads(
        (account_home / ".mindscape-seed.json").read_text(encoding="utf-8")
    )
    by_home = {payload["metadata"]["CODEX_HOME"]: payload for payload in payloads}

    assert account_auth["tokens"]["refresh_token"] == "stale-refresh"
    assert "auth_synced_from_home" not in account_seed
    assert "account_home_validated_at" not in account_seed
    assert str(account_home) in by_home
    assert by_home[str(account_home)]["metadata"]["HOME"] == str(account_home)
    assert by_home[str(codex_primary)]["pool_enabled"] is True
    assert "codex_primary_auth_vacated" not in by_home[str(codex_primary)]["metadata"]
    assert (codex_primary / "auth.json").exists()
    archived = list((managed_root / "captured-primary-auth").glob("*.auth.json"))
    assert archived == []

def test_host_ws_client_does_not_vacate_primary_when_matching_account_home_is_current(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    primary_auth = {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-05-06T20:41:50+00:00",
        "tokens": {
            "account_id": "acct-a",
            "access_token": "fresh-access",
            "refresh_token": "fresh-refresh",
            "id_token": _fake_jwt(
                {
                    "email": "account-a@example.com",
                    "sub": "google-oauth2|account-a",
                    "https://api.openai.com/auth": {
                        "chatgpt_user_id": "user-a",
                        "chatgpt_account_id": "acct-a",
                    },
                }
            ),
        },
    }
    (codex_primary / "auth.json").write_text(
        json.dumps(primary_auth),
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
                "updated_at": "2026-05-06T20:41:50+00:00",
                "login_email": "account-a@example.com",
                "auth_account_id": "acct-a",
                "auth_chatgpt_user_id": "user-a",
                "auth_synced_at": "2026-05-06T20:41:50+00:00",
                "account_home_validated_at": "2026-05-06T20:41:50+00:00",
            }
        ),
        encoding="utf-8",
    )
    (account_home / "auth.json").write_text(
        json.dumps(primary_auth),
        encoding="utf-8",
    )
    os.utime(account_home / "auth.json", (1_778_200_000, 1_778_200_000))
    os.utime(codex_primary / "auth.json", (1_778_200_000, 1_778_200_000))

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

    account_auth = json.loads((account_home / "auth.json").read_text(encoding="utf-8"))
    assert account_auth["tokens"]["refresh_token"] == "fresh-refresh"
    assert str(account_home) in by_home
    assert by_home[str(account_home)]["metadata"]["codex_seed_kind"] == "account_snapshot"
    assert by_home[str(account_home)]["metadata"]["HOME"] == str(account_home)
    assert by_home[str(codex_primary)]["pool_enabled"] is True
    assert "codex_primary_auth_vacated" not in by_home[str(codex_primary)]["metadata"]
    assert (codex_primary / "auth.json").exists()
    archived = list((managed_root / "captured-primary-auth").glob("*.auth.json"))
    assert archived == []

def test_host_ws_client_registers_unadopted_managed_account_snapshots_as_pool_members(
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
                "updated_at": "2026-05-06T00:10:00+00:00",
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
    assert (
        by_home[str(account_home)]["metadata"]["codex_pool_membership_state"]
        == "account_snapshot_registered"
    )

def test_host_ws_client_managed_mirror_registry_does_not_persist_generated_homes(
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
    assert not any(path.startswith(str(managed_root)) for path in paths)

def test_host_ws_client_does_not_persist_current_primary_as_managed_account_home(
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
    assert snapshot_paths == []
