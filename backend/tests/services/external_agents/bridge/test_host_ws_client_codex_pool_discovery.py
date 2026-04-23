import json

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
)


def test_discover_codex_home_candidates_includes_managed_account_pool(
    monkeypatch,
    tmp_path,
) -> None:
    home_dir = tmp_path / "home"
    managed_pool_root = tmp_path / "managed-pool"
    registry_path = tmp_path / "codex_host_session_seeds.json"
    account_home = managed_pool_root / "accounts" / "acct-demo"
    account_home.mkdir(parents=True)
    (account_home / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv(
        "MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT",
        str(managed_pool_root),
    )
    monkeypatch.setenv(
        "MINDSCAPE_CODEX_HOME_SEED_REGISTRY",
        str(registry_path),
    )

    client = HostBridgeWSClient(
        workspace_id="ws-test",
        surface="codex_cli",
    )

    discovered = client._discover_codex_home_candidates()
    assert str(account_home) in discovered
    assert "managed_account_pool" in discovered[str(account_home)]
