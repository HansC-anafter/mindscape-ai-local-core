from pathlib import Path
from types import SimpleNamespace

from backend.app.routes.core.system_settings import backup_config, backup_handlers, backup_models, backup_state, backups


def test_backups_facade_preserves_router_and_route_paths():
    assert backups.router is backup_handlers.router
    route_paths = {route.path for route in backups.router.routes}
    assert "/backups/local-runtime" in route_paths
    assert "/backups/local-runtime/config" in route_paths
    assert "/backups/local-runtime/dry-run" in route_paths
    assert "/backups/local-runtime/start" in route_paths
    assert "/backups/local-runtime/verify" in route_paths
    assert "/backups/local-runtime/google-drive/prepare" in route_paths


def test_backups_facade_exports_models_and_helpers():
    assert backups.LocalRuntimeBackupConfig is backup_models.LocalRuntimeBackupConfig
    assert backups._load_config is backup_config._load_config
    assert backups._latest_backup is backup_state._latest_backup
    assert backups._call_backup_job is backup_state._call_backup_job
    assert backup_handlers.Path is Path
    assert backup_state._normalize_mirror_scopes is backup_config._normalize_mirror_scopes


def test_backup_config_helpers_keep_single_policy_path():
    config = backups.LocalRuntimeBackupConfig(
        backup_root="/primary",
        mirror_root="/mirror",
        retention_local_count=5,
        retention_mirror_count=2,
        min_free_gb=12.5,
        require_mirror=True,
        base_interval_hours=72,
        mirror_scopes=["blob_storage", "postgres_chain", "blob_storage"],
    )

    flags = backups._option_flags(config)

    assert backups._normalize_mirror_scopes(["blob_storage", "postgres_chain", "blob_storage"]) == [
        "blob_storage",
        "postgres_chain",
    ]
    assert flags == [
        "--retention-local-count",
        "5",
        "--retention-mirror-count",
        "2",
        "--min-free-gb",
        "12.5",
        "--require-mirror",
        "true",
        "--base-interval-hours",
        "72",
        "--mirror-scopes",
        "blob_storage,postgres_chain",
        "--output-dir",
        "/primary",
        "--mirror-root",
        "/mirror",
    ]


def test_backup_localhost_guard_keeps_docker_and_loopback_allowlist():
    loopback_request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
    docker_request = SimpleNamespace(client=SimpleNamespace(host="172.18.0.2"), headers={})
    forwarded_request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.5"),
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    remote_request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.10"), headers={})

    assert backups._is_localhost(loopback_request) is True
    assert backups._is_localhost(docker_request) is True
    assert backups._is_localhost(forwarded_request) is True
    assert backups._is_localhost(remote_request) is False
