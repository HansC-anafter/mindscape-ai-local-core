from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.origin import (
    LOCKED_HOST_BINDINGS,
    OriginTopologyGate,
)
from remote_workbench_authorization_cutover.origin_recovery import (
    recover_persisted_reconcile_state,
    recover_pre_active_services,
)
from remote_workbench_authorization_cutover.resources import ResourceSnapshot
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
    return yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _environment_names(service: dict) -> set[str]:
    values = service.get("environment") or []
    if isinstance(values, dict):
        return set(values)
    return {str(value).split("=", 1)[0] for value in values}


def test_remote_workbench_origin_ports_are_loopback_or_internal_only() -> None:
    services = _compose()["services"]

    assert "127.0.0.1:8200:8200" in services["backend"]["ports"]
    assert (
        "127.0.0.1:3002-3020:3002-3020"
    ) in services["backend"]["ports"]
    assert (
        "127.0.0.1:8220:8210"
        in services["backend-control"]["ports"]
    )
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
    assert (
        "tunnel --no-autoupdate --metrics 0.0.0.0:2000 run"
        in source
    )
    assert "--token-file /etc/cloudflared/tunnel-token" in source
    assert source.count('--token-path "$TOKEN_PATH"') == 2
    assert 'expected_command=\'["tunnel","--no-autoupdate","--metrics"' in source
    assert "{{json .Config.Cmd}}" in source


def test_bridge_plist_has_exact_argument_vector_without_legacy_run() -> None:
    template = (REPO_ROOT / "scripts/config/ai.mindscape.remote-workbench-bridge.plist").read_text(
        encoding="utf-8"
    )

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
    installer = (REPO_ROOT / "scripts/install-remote-workbench-bridge-macos.sh").read_text(
        encoding="utf-8"
    )
    assert "maintenance enter supervisor_activation" in installer
    assert "maintenance.json" not in installer
    bootout = installer.index('"$LAUNCHCTL_BIN" bootout')
    maintenance = installer.index('"$LAUNCHER" maintenance enter supervisor_activation')
    bootstrap = installer.index('"$LAUNCHCTL_BIN" bootstrap')
    assert bootout < maintenance < bootstrap


def _service_ports(bindings: dict[tuple[int, str], int]) -> dict:
    return {
        "ports": [
            {
                "target": str(target),
                "published": str(published),
                "protocol": protocol,
                "host_ip": "127.0.0.1",
            }
            for (target, protocol), published in sorted(bindings.items())
        ]
    }


def _locked_config() -> dict:
    return {
        "name": "mindscape-ai-local-core",
        "services": {
            name: _service_ports(bindings)
            for name, bindings in LOCKED_HOST_BINDINGS.items()
        },
    }


class NoopExecutor:
    def run(self, _args, **_kwargs) -> str:
        return ""


class InspectExecutor:
    def __init__(self, inspect: dict) -> None:
        self.inspect = inspect

    def run(self, args, **_kwargs) -> str:
        if list(args)[:2] == ["docker", "inspect"]:
            return json.dumps([self.inspect])
        return "container-id"


def test_origin_gate_has_independent_exact_service_host_port_lock() -> None:
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=NoopExecutor())
    config = _locked_config()
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


def test_declared_read_only_bind_mount_rejects_live_rw_mount(tmp_path: Path) -> None:
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
    config = _locked_config()
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
        lambda _workspace: pytest.fail("missing frontend must not be docker-exec probed"),
    )

    result = gate.inspect(tmp_path, "workspace-a")

    assert result["internal_listener"] == {
        "state": "closed",
        "reason": "frontend_unavailable_before_reconcile",
    }
    assert result["drift"]["frontend"] == ["container_missing"]


class RecoveryExecutor:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args, **_kwargs) -> str:
        command = list(args)
        self.calls.append(command)
        if command[:4] == [
            "docker",
            "exec",
            "mindscape-ai-local-core-redis",
            "redis-cli",
        ]:
            return json.dumps(
                {
                    "totals": {"pending": 0, "processing": 0, "delayed": 0, "deadletter": 0},
                    "inventory": [],
                    "runners": {"count": 1, "capacity": 2, "inflight": 0, "malformed": 0},
                }
            )
        return ""


def test_origin_recovery_restores_only_pre_active_mutation_set_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)
    pre_active = {"postgres", "pgbouncer", "backend", "frontend", "runner-apple"}
    monkeypatch.setattr(
        gate,
        "_active_services",
        lambda _project: pre_active | {"backend-control"},
    )
    inspected: list[str] = []
    monkeypatch.setattr(
        gate,
        "_inspect_service",
        lambda name, _expected: (inspected.append(name) or {}, []),
    )
    config = {
        "name": "mindscape-ai-local-core",
        "services": {name: {} for name in pre_active | {"backend-control"}},
    }
    before = ResourceSnapshot(
        totals={"pending": 0, "processing": 0, "delayed": 0, "deadletter": 0},
        inventory=(),
        runners={"count": 1, "capacity": 2, "inflight": 0},
    )

    recover_pre_active_services(
        gate,
        config=config,
        pre_active_services=pre_active,
        mutated_services=["postgres", "backend-control"],
        stopped_dependents=["backend", "frontend", "runner-apple"],
        before=before,
    )

    compose_calls = [call for call in executor.calls if call[:2] == ["docker", "compose"]]
    assert compose_calls[0][-2:] == ["stop", "backend-control"]
    assert compose_calls[1][-1] == "postgres"
    assert compose_calls[2][-2:] == ["backend", "frontend"]
    assert compose_calls[3][-1] == "runner-apple"
    assert set(inspected) == pre_active


def test_completed_origin_reconcile_receipt_is_exact_noop(
    tmp_path: Path,
) -> None:
    state = tmp_path / "origin-reconcile-state.json"
    state.write_text(
        json.dumps(
            {
                "reconcile_completed": True,
                "pre_active_services": ["frontend"],
                "mutated_services": ["frontend"],
                "stopped_dependents": [],
                "runner_count": 0,
                "runner_capacity": 0,
            }
        ),
        encoding="utf-8",
    )
    state.chmod(0o600)
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)

    assert recover_persisted_reconcile_state(gate, tmp_path) is False
    assert executor.calls == []
    readback = json.loads(
        (tmp_path / "origin-recovery-readback.json").read_text(encoding="utf-8")
    )
    assert readback["reconcile_completed"] is True


def test_internal_listener_probe_distinguishes_host_gate_from_missing_token() -> None:
    class ListenerExecutor:
        def __init__(self, rows): self.rows = rows
        def run(self, _args, **_kwargs): return json.dumps(self.rows)

    rows = [
        {
            "host": "spoof.invalid",
            "status": 403,
            "stage": "identity_rejected",
            "reason": "invalid_public_host",
        },
        {
            "host": "localhost",
            "status": 403,
            "stage": "identity_rejected",
            "reason": "invalid_public_host",
        },
        {
            "host": "remote-workbench.mindscapeai.app",
            "status": 403,
            "stage": "identity_rejected",
            "reason": "missing_access_token",
        },
    ]
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=ListenerExecutor(rows))
    assert gate._internal_listener_probe("workspace-a")["state"] == "default_deny"

    rows[0]["reason"] = "missing_access_token"
    with pytest.raises(CutoverError, match="did not default deny"):
        gate._internal_listener_probe("workspace-a")
