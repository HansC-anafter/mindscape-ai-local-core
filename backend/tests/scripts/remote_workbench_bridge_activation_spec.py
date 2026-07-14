from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_bridge.activation import (
    ActivationError,
    source_build_id,
    verify_activation,
)
from remote_workbench_remote_ingress_lock import (
    IngressLockError,
    canonical_config_sha256,
    live_projection,
    load_lock,
    parse_live_config_version,
)


TUNNEL_ID = "7f3f91d3-e0a7-4bba-8c7c-a5a979ab54ea"
NOW = datetime(2026, 7, 13, 8, 30, tzinfo=timezone.utc)


def _lock_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "tunnel_id": TUNNEL_ID,
        "config_version": 17,
        "config_sha256": canonical_config_sha256(),
        "config_src": "cloudflare",
        "hostname": "remote-workbench.mindscapeai.app",
        "service": "http://mindscape-ai-local-core-frontend:3001",
        "catch_all": "http_status:404",
        "verified_at": "2026-07-13T08:29:59.123456Z",
    }
    payload.update(overrides)
    return payload


def _write_lock(tmp_path: Path, payload: dict[str, object]) -> Path:
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "remote-ingress-lock.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _metrics(*, version: str = "17") -> bytes:
    return (
        "# HELP cloudflared_orchestration_config_version Configuration Version\n"
        "# TYPE cloudflared_orchestration_config_version gauge\n"
        f"cloudflared_orchestration_config_version {version}\n"
    ).encode("utf-8")


def test_remote_ingress_lock_requires_exact_cloudflare_topology_and_live_version(
    tmp_path: Path,
) -> None:
    assert canonical_config_sha256() == (
        "9fe62f75ad018e404b2146f7d8462ec8fc72a52e535c3fab8f7d9b5a67ac9948"
    )
    lock = load_lock(_write_lock(tmp_path, _lock_payload()))
    metrics = _metrics()

    payload = live_projection(
        lock,
        parse_live_config_version(metrics),
    )

    assert payload["remote_ingress_verified"] is True
    assert payload["metric_version"] == 17


@pytest.mark.parametrize(
    "override,code",
    [
        ({"unexpected": True}, "ingress_lock_schema_mismatch"),
        ({"config_src": "local"}, "ingress_lock_topology_mismatch"),
        ({"service": "http://127.0.0.1:8300"}, "ingress_lock_topology_mismatch"),
        ({"config_sha256": "0" * 64}, "ingress_lock_config_hash_mismatch"),
        ({"verified_at": "2026-07-13T08:29:59+00:00"}, "ingress_lock_verified_at_malformed"),
    ],
)
def test_remote_ingress_lock_rejects_aliases_and_semantic_drift(
    tmp_path: Path,
    override: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(IngressLockError, match=code):
        load_lock(_write_lock(tmp_path, _lock_payload(**override)))


def test_remote_ingress_live_projection_rejects_version_drift(
    tmp_path: Path,
) -> None:
    lock = load_lock(_write_lock(tmp_path, _lock_payload()))
    with pytest.raises(IngressLockError, match="connector_config_version_drift"):
        live_projection(lock, 16)


def test_remote_ingress_lock_requires_parent_0700_and_file_0600(
    tmp_path: Path,
) -> None:
    path = _write_lock(tmp_path, _lock_payload())
    os.chmod(path, 0o644)
    with pytest.raises(IngressLockError, match="ingress_lock_mode_mismatch"):
        load_lock(path)
    os.chmod(path, 0o600)
    os.chmod(tmp_path, 0o755)
    with pytest.raises(IngressLockError, match="ingress_lock_parent_mode_mismatch"):
        load_lock(path)


@pytest.mark.parametrize(
    "metrics",
    [
        b'cloudflared_orchestration_config_version{source="test"} 17\n',
        b"cloudflared_orchestration_config_version 17\ncloudflared_orchestration_config_version 17\n",
        b"cloudflared_orchestration_config_version 17.5\n",
    ],
)
def test_live_config_version_metric_is_one_unlabelled_integer(metrics: bytes) -> None:
    with pytest.raises(IngressLockError, match="connector_config_version_metric"):
        parse_live_config_version(metrics)


def _activation_fixture(tmp_path: Path, *, extra_argument: str | None = None) -> dict:
    build_id = source_build_id(REPO_ROOT)
    python_bin = Path(sys.executable)
    monitor = REPO_ROOT / "scripts/remote_workbench_bridge_monitor.py"
    argv = [str(python_bin), str(monitor)]
    plist_path = tmp_path / "ai.mindscape.remote-workbench-bridge.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "ai.mindscape.remote-workbench-bridge",
                "ProgramArguments": argv,
                "WorkingDirectory": str(REPO_ROOT),
                "RunAtLoad": True,
                "KeepAlive": {"SuccessfulExit": False},
                "ThrottleInterval": 10,
                "StandardOutPath": str(
                    REPO_ROOT / "logs/remote-workbench-bridge.log"
                ),
                "StandardErrorPath": str(
                    REPO_ROOT / "logs/remote-workbench-bridge.error.log"
                ),
                "EnvironmentVariables": {
                    "HOME": str(tmp_path),
                    "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "DOCKER_HOST": f"unix://{tmp_path}/.docker/run/docker.sock",
                    "REMOTE_WORKBENCH_BRIDGE_BUILD_ID": build_id,
                    "REMOTE_WORKBENCH_PROJECT_ROOT": str(REPO_ROOT),
                    "REMOTE_WORKBENCH_BRIDGE_STATE_DIR": str(tmp_path),
                },
            }
        )
    )
    os.chmod(plist_path, 0o600)
    status_path = tmp_path / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "checked_at": NOW.isoformat(),
                "maintenance": {"enabled": True},
                "poll_interval_seconds": 20.0,
                "ready": False,
                "state": "maintenance",
                "supervisor_build_id": build_id,
                "supervisor_pid": 4242,
            }
        ),
        encoding="utf-8",
    )
    os.chmod(status_path, 0o600)
    launch_argv = argv + ([extra_argument] if extra_argument else [])
    arguments = "\n".join(f"        {value}" for value in launch_argv)
    launchd_output = f"""
state = running
program = {python_bin}
arguments = {{
{arguments}
}}
environment = {{
    REMOTE_WORKBENCH_BRIDGE_BUILD_ID => {build_id}
}}
pid = 4242
"""
    return {
        "project_root": REPO_ROOT,
        "python_bin": python_bin,
        "installed_plist": plist_path,
        "launchd_output": launchd_output,
        "status_path": status_path,
        "now": NOW,
    }


def test_activation_verifies_current_build_exact_argv_pid_and_maintenance(
    tmp_path: Path,
) -> None:
    payload = verify_activation(**_activation_fixture(tmp_path))

    assert set(payload) == {
        "activation_conformant",
        "argv",
        "checked_at",
        "current_build_id",
        "launchd_running",
        "live_build_id",
        "maintenance",
        "pid",
        "poll_interval_seconds",
        "ready",
        "state",
        "status_fresh",
        "status_freshness_limit_seconds",
    }
    assert payload["activation_conformant"] is True
    assert payload["launchd_running"] is True
    assert payload["current_build_id"] == payload["live_build_id"]
    assert payload["maintenance"] is True
    assert payload["state"] == "maintenance"


def test_activation_rejects_legacy_run_argument(tmp_path: Path) -> None:
    with pytest.raises(ActivationError, match="launchd_arguments_mismatch"):
        verify_activation(**_activation_fixture(tmp_path, extra_argument="run"))


def test_activation_rejects_non_running_launchd_process(tmp_path: Path) -> None:
    fixture = _activation_fixture(tmp_path)
    fixture["launchd_output"] = fixture["launchd_output"].replace(
        "state = running", "state = exited"
    )
    with pytest.raises(ActivationError, match="launchd_state_mismatch"):
        verify_activation(**fixture)


def test_activation_rejects_operational_maintenance_state_mismatch(
    tmp_path: Path,
) -> None:
    fixture = _activation_fixture(tmp_path)
    status_path = fixture["status_path"]
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["maintenance"] = {"enabled": False}
    status_path.write_text(json.dumps(status), encoding="utf-8")
    os.chmod(status_path, 0o600)

    with pytest.raises(ActivationError, match="supervisor_status_maintenance_mismatch"):
        verify_activation(**fixture)


def test_activation_freshness_uses_checked_at_and_actual_bounded_poll(
    tmp_path: Path,
) -> None:
    fixture = _activation_fixture(tmp_path)
    status_path = fixture["status_path"]
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["poll_interval_seconds"] = 300.0
    status["checked_at"] = (NOW - timedelta(seconds=899)).isoformat()
    status_path.write_text(json.dumps(status), encoding="utf-8")
    os.chmod(status_path, 0o600)

    assert verify_activation(**fixture)["status_freshness_limit_seconds"] == 900.0

    status["checked_at"] = (NOW - timedelta(seconds=901)).isoformat()
    status_path.write_text(json.dumps(status), encoding="utf-8")
    os.chmod(status_path, 0o600)
    with pytest.raises(ActivationError, match="supervisor_status_stale"):
        verify_activation(**fixture)


@pytest.mark.parametrize(
    ("field", "value"),
    [("supervisor_build_id", "old-build"), ("supervisor_pid", 0)],
)
def test_activation_rejects_old_build_or_dead_status_pid(
    tmp_path: Path, field: str, value: object
) -> None:
    fixture = _activation_fixture(tmp_path)
    status_path = fixture["status_path"]
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status[field] = value
    status_path.write_text(json.dumps(status), encoding="utf-8")
    os.chmod(status_path, 0o600)

    with pytest.raises(ActivationError, match="supervisor_status_identity_mismatch"):
        verify_activation(**fixture)


def test_monitor_build_id_cli_matches_activation_digest() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/remote_workbench_bridge_monitor.py", "--build-id"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == source_build_id(REPO_ROOT)


def _fake_docker(tmp_path: Path) -> Path:
    binary = tmp_path / "docker"
    binary.write_text(
        """#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
if args[:2] == ["image", "inspect"]:
    if "{{json .Config.Env}}" in args:
        print('["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt"]')
    elif "{{.Config.User}}" in args:
        print("65532:65532")
    else:
        print("sha256:fixed-image-id")
    raise SystemExit(0)
if args and args[0] == "inspect" and "-f" not in args:
    raise SystemExit(0)
if args[:2] == ["inspect", "-f"]:
    template = args[2]
    values = {
        "{{.State.Running}}": os.environ.get("FAKE_RUNNING", "true"),
        "{{.HostConfig.RestartPolicy.Name}}": "unless-stopped",
        "{{.HostConfig.NetworkMode}}": "mindscape-network",
        "{{len .Mounts}}": "1",
        "{{json .HostConfig.PortBindings}}": '{"2000/tcp":[{"HostIp":"127.0.0.1","HostPort":"2000"}]}',
        "{{.Config.Image}}": "cloudflare/cloudflared@sha256:ba461b8aa9c042156dbd39c38657fe7431bafa063220eab8d5330a523863da9f",
        "{{.Image}}": "sha256:fixed-image-id",
        "{{json .Config.Env}}": '["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt"]',
        "{{.Config.User}}": "65532:65532",
        "{{.HostConfig.Privileged}}": "false",
        "{{json .Config.Entrypoint}}": '["cloudflared","--no-autoupdate"]',
        "{{json .Config.Cmd}}": os.environ["FAKE_CLOUDFLARED_COMMAND"],
    }
    if "Source" in template:
        print(os.environ["FAKE_TOKEN_PATH"])
    elif "RW" in template:
        print("false")
    elif "Type" in template:
        print("bind")
    elif template in values:
        print(values[template])
    else:
        raise SystemExit(3)
    raise SystemExit(0)
raise SystemExit(3)
""",
        encoding="utf-8",
    )
    os.chmod(binary, 0o700)
    return binary


def _launcher_status(tmp_path: Path, command: list[str]) -> dict:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True)
    docker = _fake_docker(fake_bin)
    assert docker.name == "docker"
    state = tmp_path / "state"
    state.mkdir()
    os.chmod(state, 0o700)
    token = tmp_path / "tunnel-token"
    token.write_text("opaque-test-token", encoding="utf-8")
    os.chmod(token, 0o600)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "REMOTE_WORKBENCH_BRIDGE_PYTHON_BIN": sys.executable,
            "REMOTE_WORKBENCH_BRIDGE_STATE_DIR": str(state),
            "REMOTE_WORKBENCH_CLOUDFLARED_TOKEN_FILE": str(token),
            "FAKE_TOKEN_PATH": str(token),
            "FAKE_CLOUDFLARED_COMMAND": json.dumps(command, separators=(",", ":")),
        }
    )
    result = subprocess.run(
        ["scripts/start_remote_workbench_tunnel.sh", "status", "--json"],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_container_contract_requires_exact_token_only_command_without_extra_origin(
    tmp_path: Path,
) -> None:
    expected = [
        "tunnel",
        "--no-autoupdate",
        "--metrics",
        "0.0.0.0:2000",
        "run",
        "--token-file",
        "/etc/cloudflared/tunnel-token",
    ]
    valid = _launcher_status(tmp_path / "valid", expected)
    invalid = _launcher_status(tmp_path / "invalid", expected + ["--url", "http://bad"])

    assert valid["container_contract_conformant"] is True
    assert valid["contract_conformant"] is False
    assert valid["remote_ingress_verified"] is False
    assert invalid["container_contract_conformant"] is False


def test_stop_remains_available_without_python_or_ingress_helpers(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _fake_docker(fake_bin)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "REMOTE_WORKBENCH_BRIDGE_PYTHON_BIN": str(tmp_path / "missing-python"),
            "FAKE_RUNNING": "false",
            "FAKE_CLOUDFLARED_COMMAND": "[]",
            "FAKE_TOKEN_PATH": str(tmp_path / "missing-token"),
        }
    )

    result = subprocess.run(
        ["scripts/start_remote_workbench_tunnel.sh", "stop"],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0


def _activation_shell(tmp_path: Path, stop_body: str) -> subprocess.CompletedProcess[str]:
    state = tmp_path / "state"
    script = f"""
set -euo pipefail
export HOME={json.dumps(str(tmp_path))}
export REMOTE_WORKBENCH_BRIDGE_STATE_DIR={json.dumps(str(state))}
source {json.dumps(str(REPO_ROOT / 'scripts/start_remote_workbench_tunnel.sh'))}
uname() {{ printf 'Darwin\n'; }}
supervisor_loaded() {{ return 1; }}
docker_available() {{ return 0; }}
stop_tunnel() {{ {stop_body}; }}
tunnel_closed() {{ return 0; }}
maintenance_enter supervisor_activation
"""
    return subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )


def test_supervisor_activation_writes_maintenance_before_stopping_tunnel(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    events = tmp_path / "events"
    stop_body = (
        '[[ -f "$MAINTENANCE_FILE" ]] || return 91; '
        f"printf 'stop\\n' > {json.dumps(str(events))}; return 0"
    )

    result = _activation_shell(tmp_path, stop_body)

    assert result.returncode == 0, result.stderr
    assert events.read_text(encoding="utf-8") == "stop\n"
    assert json.loads((state / "maintenance.json").read_text(encoding="utf-8"))[
        "reason"
    ] == "supervisor_activation"


def test_supervisor_activation_fails_closed_when_tunnel_stop_fails(
    tmp_path: Path,
) -> None:
    result = _activation_shell(tmp_path, "return 1")

    assert result.returncode != 0
    assert "Tunnel stop failed during supervisor activation" in result.stderr
    assert (tmp_path / "state/maintenance.json").is_file()
