from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict:
    return yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_delivers_vector_password_only_as_service_secret():
    compose_source = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = _compose()
    secret_name = "postgres_vector_runtime_password"

    assert compose["secrets"][secret_name] == {
        "environment": "POSTGRES_VECTOR_RUNTIME_PASSWORD"
    }
    assert "${POSTGRES_VECTOR_RUNTIME_PASSWORD" not in compose_source
    assert "DATABASE_URL_VECTOR=postgresql://" not in compose_source
    for service_name in (
        "backend",
        "backend-control",
        "postgres",
        "postgres-vector-runtime-bootstrap",
        "pgbouncer",
    ):
        assert secret_name in compose["services"][service_name]["secrets"]

    runner = compose["x-runner-common"]
    assert secret_name in runner["secrets"]


def test_bootstrap_is_bounded_and_pgbouncer_waits_for_completion():
    services = _compose()["services"]
    bootstrap = services["postgres-vector-runtime-bootstrap"]
    pgbouncer = services["pgbouncer"]

    assert bootstrap["restart"] == "no"
    assert "ports" not in bootstrap
    assert bootstrap["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert (
        pgbouncer["depends_on"]["postgres-vector-runtime-bootstrap"]["condition"]
        == "service_completed_successfully"
    )


def test_secret_change_preserves_pool_runner_port_and_ux_contracts():
    compose = _compose()
    compose_source = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    pgbouncer = (REPO_ROOT / "docker/pgbouncer/pgbouncer.ini").read_text(
        encoding="utf-8"
    )

    assert "pool_mode = transaction" in pgbouncer
    assert "default_pool_size = 30" in pgbouncer
    assert "min_pool_size = 5" in pgbouncer
    assert "reserve_pool_size = 10" in pgbouncer
    assert "max_client_conn = 500" in pgbouncer
    runner_inflight_defaults = (
        ("runner-default-local-browser", "LOCAL_CORE_RUNNER_DEFAULT_LOCAL_BROWSER_MAX_INFLIGHT:-2"),
        ("runner-browser", "LOCAL_CORE_RUNNER_BROWSER_MAX_INFLIGHT:-2"),
        ("runner-browser-extra", "LOCAL_CORE_RUNNER_BROWSER_EXTRA_MAX_INFLIGHT:-2"),
        ("runner-vision", "LOCAL_CORE_RUNNER_VISION_MAX_INFLIGHT:-1"),
    )
    for service_name, expected_default in runner_inflight_defaults:
        assert expected_default in compose["services"][service_name]["environment"][
            "LOCAL_CORE_RUNNER_MAX_INFLIGHT"
        ]
    default_browser = compose["services"]["runner-default-local-browser"]
    assert "mem_limit" not in default_browser
    assert "cpus" not in default_browser
    assert "pids_limit" not in default_browser
    assert '"127.0.0.1:8200:8200"' in compose_source
    assert '"127.0.0.1:8300:3000"' in compose_source
    assert "refetchInterval" not in compose_source


def test_reconcile_and_pgbouncer_scripts_never_put_secret_in_argv():
    postgres_init = (REPO_ROOT / "docker/postgres/init-dual-dbs.sh").read_text(
        encoding="utf-8"
    )
    reconcile = (
        REPO_ROOT / "docker/postgres/reconcile-vector-runtime-role.sh"
    ).read_text(encoding="utf-8")
    pgbouncer_start = (REPO_ROOT / "docker/pgbouncer/start.sh").read_text(
        encoding="utf-8"
    )

    assert "--set=runtime_secret" not in reconcile
    assert "\\getenv runtime_secret POSTGRES_VECTOR_RUNTIME_PASSWORD" in reconcile
    assert "vector runtime role already converged" in reconcile
    assert "umask 077" in pgbouncer_start
    assert "exec /usr/sbin/pgbouncer" in pgbouncer_start
    for consumer in (postgres_init, reconcile, pgbouncer_start):
        assert "tr -d '\\n'" not in consumer
        assert "exactly one line" in consumer


def test_product_restart_instructions_use_secret_aware_facades():
    command_facade = (
        REPO_ROOT / "backend/app/runtime_secret_command_facade.py"
    ).read_text(encoding="utf-8")
    locale_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            REPO_ROOT
            / "web-console/src/lib/i18n/locales/en/settingsSections/workspaceResources.ts",
            REPO_ROOT
            / "web-console/src/lib/i18n/locales/zh-TW/settingsSections/workspaceResources.ts",
            REPO_ROOT / "web-console/src/lib/i18n/locales/ja/settings.ts",
        )
    )

    assert "scripts/compose.sh restart" in command_facade
    assert "scripts\\\\compose.ps1 restart" in command_facade
    assert "docker compose restart backend" not in locale_sources
