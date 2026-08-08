from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml


TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))

from remote_workbench_origin_test_support import (
    REPO_ROOT,
    InspectExecutor,
    NoopExecutor,
    locked_config,
)
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.origin import OriginTopologyGate


LEGACY_AUTH_ENV_NAMES = {
    "MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES",
    "MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS",
    "MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_GROUPS",
    "MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST",
    "MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE",
    "MOBILE_WORKBENCH_GATEWAY_JWT_ISSUER",
    "MOBILE_WORKBENCH_GATEWAY_JWT_CLOCK_SKEW_SECONDS",
    "MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY",
    "MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_FILE",
    "MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION",
}


def _compose() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )


def _environment_names(service: dict) -> set[str]:
    values = service.get("environment") or []
    if isinstance(values, dict):
        return set(values)
    return {str(value).split("=", 1)[0] for value in values}


def test_remote_workbench_origin_ports_are_loopback_or_internal_only() -> None:
    services = _compose()["services"]

    assert "127.0.0.1:8200:8200" in services["backend"]["ports"]
    assert ("127.0.0.1:3002-3020:3002-3020") in services["backend"]["ports"]
    assert "127.0.0.1:8220:8210" in services["backend-control"]["ports"]
    assert services["pgbouncer"]["ports"] == ["127.0.0.1:6432:6432"]
    assert services["postgres-replica"]["ports"] == ["127.0.0.1:5434:5432"]
    assert services["postgres"]["ports"] == ["127.0.0.1:5433:5432"]
    assert services["redis"]["ports"] == ["127.0.0.1:6379:6379"]
    assert services["ocr-service"]["ports"] == ["127.0.0.1:8001:8001"]
    assert services["media-proxy"]["ports"] == ["127.0.0.1:8202:8000"]
    assert services["xtts-service"]["ports"] == ["127.0.0.1:8020:8020"]
    assert services["whisper-service"]["ports"] == ["127.0.0.1:8006:8006"]
    assert services["frontend"]["ports"] == ["127.0.0.1:8300:3000"]
    assert services["frontend"]["expose"] == ["3001"]
    published = [
        str(port)
        for service in services.values()
        for port in (service.get("ports") or [])
    ]
    assert published
    assert all(port.startswith("127.0.0.1:") for port in published)
    rendered = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for override in (
        "${SANDBOX_PREVIEW_PORT_START:-3002}-${SANDBOX_PREVIEW_PORT_END:-3020}",
        "${MINDSCAPE_CONTROL_PLANE_HOST_PORT:-8220}",
        "${LOCAL_CORE_PGBOUNCER_HOST_PORT:-6432}",
        "${LOCAL_CORE_POSTGRES_REPLICA_HOST_PORT:-5434}",
    ):
        assert override not in rendered


def test_frontend_uses_dedicated_internal_remote_listener() -> None:
    frontend = _compose()["services"]["frontend"]
    environment = frontend["environment"]

    assert "NEXT_DEV_PORT=3002" in environment
    assert LEGACY_AUTH_ENV_NAMES.isdisjoint(_environment_names(frontend))
    assert "MOBILE_WORKBENCH_GATEWAY_ENABLED" in _environment_names(frontend)
    assert "MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN" in _environment_names(frontend)


def test_canonical_launcher_targets_only_the_internal_listener() -> None:
    source = (REPO_ROOT / "scripts/start_remote_workbench_tunnel.sh").read_text(
        encoding="utf-8"
    )

    assert 'NETWORK_NAME="mindscape-network"' in source
    assert 'INTERNAL_TARGET="http://mindscape-ai-local-core-frontend:3001"' in source
    assert "http://host.docker.internal:8300" not in source
    assert "http://127.0.0.1:8300" not in source
    assert "http://localhost:8300" not in source


def test_canonical_launcher_uses_one_immutable_remote_managed_tunnel_command() -> None:
    source = (REPO_ROOT / "scripts/start_remote_workbench_tunnel.sh").read_text(
        encoding="utf-8"
    )

    assert (
        'CLOUDFLARED_IMAGE="cloudflare/cloudflared@sha256:'
        'ba461b8aa9c042156dbd39c38657fe7431bafa063220eab8d5330a523863da9f"'
        in source
    )
    assert "REMOTE_WORKBENCH_CLOUDFLARED_IMAGE" not in source
    assert "cloudflare/cloudflared:latest" not in source
    assert "--config" not in source
    assert "cloudflared-config" not in source
    assert "tunnel --no-autoupdate --metrics 0.0.0.0:2000 run" in source
    assert "--token-file /etc/cloudflared/tunnel-token" in source
    assert source.count('--token-path "$TOKEN_PATH"') == 2
    assert 'expected_command=\'["tunnel","--no-autoupdate","--metrics"' in source
    assert "{{json .Config.Cmd}}" in source


def test_origin_recovery_is_fixed_to_the_frontend_service() -> None:
    source = (REPO_ROOT / "scripts/start_remote_workbench_tunnel.sh").read_text(
        encoding="utf-8"
    )

    assert (
        'docker compose -f "$PROJECT_ROOT/docker-compose.yml" '
        "up -d --force-recreate --no-deps frontend"
    ) in source
    assert "recover-origin accepts no additional arguments" in source
    assert "recover_origin" in source


def test_bridge_plist_has_exact_argument_vector_without_legacy_run() -> None:
    template = (
        REPO_ROOT / "scripts/config/ai.mindscape.remote-workbench-bridge.plist"
    ).read_text(encoding="utf-8")

    assert template.count("<key>ProgramArguments</key>") == 1
    argument_block = template.split("<key>ProgramArguments</key>", 1)[1].split(
        "</array>", 1
    )[0]
    assert argument_block.count("<string>") == 2
    assert "remote_workbench_bridge_monitor.py" in argument_block
    assert "<string>run</string>" not in argument_block
    assert "REMOTE_WORKBENCH_BRIDGE_BUILD_ID" in template


def test_launcher_is_the_only_maintenance_file_writer() -> None:
    writers = []
    for path in (REPO_ROOT / "scripts").rglob("*"):
        if path.suffix not in {".py", ".sh"} or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8")
        if ".maintenance.XXXXXX" in body or 'rm -f "$MAINTENANCE_FILE"' in body:
            writers.append(path.relative_to(REPO_ROOT).as_posix())

    assert writers == ["scripts/start_remote_workbench_tunnel.sh"]
    installer = (
        REPO_ROOT / "scripts/install-remote-workbench-bridge-macos.sh"
    ).read_text(encoding="utf-8")
    assert "maintenance enter supervisor_activation" in installer
    assert "maintenance.json" not in installer
    bootout = installer.index('"$LAUNCHCTL_BIN" bootout')
    maintenance = installer.index('"$LAUNCHER" maintenance enter supervisor_activation')
    bootstrap = installer.index('"$LAUNCHCTL_BIN" bootstrap')
    assert bootout < maintenance < bootstrap


def test_origin_gate_has_independent_exact_service_host_port_lock() -> None:
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=NoopExecutor())
    config = locked_config()
    gate._require_locked_host_ports(config)
    config["services"]["pgbouncer"]["ports"][0]["published"] = "16432"
    with pytest.raises(CutoverError, match="host-port map changed: pgbouncer"):
        gate._require_locked_host_ports(config)


def test_build_only_service_uses_compose_identity_without_empty_image_drift() -> None:
    inspect = {
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "HostConfig": {"PortBindings": {}},
        "Config": {
            "Image": "mindscape-ai-local-core-frontend",
            "Cmd": None,
            "Labels": {
                "com.docker.compose.project": "mindscape-ai-local-core",
                "com.docker.compose.service": "frontend",
                "com.docker.compose.project.working_dir": str(REPO_ROOT),
            },
        },
        "NetworkSettings": {"Networks": {}},
        "Mounts": [],
    }
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=InspectExecutor(inspect))
    _evidence, reasons = gate._inspect_service("frontend", {"image": None})
    assert reasons == []

    inspect["Config"]["Labels"]["com.docker.compose.service"] = "rogue"
    _evidence, reasons = gate._inspect_service("frontend", {"image": None})
    assert reasons == ["compose_service"]


def test_declared_read_only_bind_mount_rejects_live_rw_mount(
    tmp_path: Path,
) -> None:
    source = str(tmp_path / "source")
    inspect = {
        "State": {"Running": True},
        "HostConfig": {"PortBindings": {}},
        "Config": {
            "Image": "runtime-image",
            "Labels": {
                "com.docker.compose.project": "mindscape-ai-local-core",
                "com.docker.compose.service": "frontend",
                "com.docker.compose.project.working_dir": str(REPO_ROOT),
            },
        },
        "NetworkSettings": {"Networks": {}},
        "Mounts": [
            {
                "Type": "bind",
                "Source": source,
                "Destination": "/app/source",
                "RW": True,
                "Mode": "rw",
                "Propagation": "rprivate",
            }
        ],
    }
    expected = {
        "image": None,
        "volumes": [
            {
                "type": "bind",
                "source": source,
                "target": "/app/source",
                "read_only": True,
                "bind": {"propagation": "rprivate"},
            }
        ],
    }
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=InspectExecutor(inspect))
    _evidence, reasons = gate._inspect_service("frontend", expected)
    assert reasons == ["bind_mounts"]


def test_origin_inspect_records_missing_frontend_closed_without_docker_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=NoopExecutor())
    config = locked_config()
    monkeypatch.setattr(gate, "_compose_config", lambda **_kwargs: config)
    monkeypatch.setattr(gate, "_active_services", lambda _project: set())
    monkeypatch.setattr(gate, "_lan_hosts", lambda: ["10.0.0.2", "192.168.1.4"])

    def inspect_service(name, _expected):
        if name == "frontend":
            return {}, ["container_missing"]
        return {"live_host_ports": []}, []

    monkeypatch.setattr(gate, "_inspect_service", inspect_service)
    monkeypatch.setattr(
        gate,
        "_internal_listener_probe",
        lambda _workspace: pytest.fail(
            "missing frontend must not be docker-exec probed"
        ),
    )

    result = gate.inspect(tmp_path, "workspace-a")

    assert result["internal_listener"] == {
        "state": "closed",
        "reason": "frontend_unavailable_before_reconcile",
    }
    assert result["drift"] == {}
    assert result["services"]["frontend"]["drift"] == ["container_missing"]
