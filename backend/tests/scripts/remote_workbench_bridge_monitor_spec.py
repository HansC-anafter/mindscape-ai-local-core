from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import remote_workbench_bridge.probes as probes_module
import remote_workbench_bridge_monitor as monitor_module
from remote_workbench_bridge.activation import KNOWN_STATES
from remote_workbench_bridge.probes import BridgeProbes, ProbeResult, _decode_chunked_body
from remote_workbench_bridge.settings import CLOUDFLARED_IMAGE, BridgeSettings
from remote_workbench_bridge.state_store import BridgeStateStore
from remote_workbench_bridge.supervisor import BridgeSupervisor


def _settings(tmp_path: Path) -> BridgeSettings:
    state_dir = tmp_path / "state"
    return BridgeSettings(
        project_root=tmp_path,
        state_dir=state_dir,
        launcher_path=tmp_path / "launcher",
        status_path=state_dir / "status.json",
        events_path=state_dir / "events.jsonl",
        maintenance_path=state_dir / "maintenance.json",
        docker_socket_path=tmp_path / "docker.sock",
        container_name="ig-workbench-cloudflared",
        network_name="mindscape-network",
        internal_target="http://mindscape-ai-local-core-frontend:3001",
        token_path=tmp_path / "tunnel-token",
        cloudflared_image=CLOUDFLARED_IMAGE,
        metrics_host_port=2000,
        local_origin_url="http://127.0.0.1:8300/healthz",
        connector_ready_url="http://127.0.0.1:2000/ready",
        public_origin_url="https://remote-workbench.mindscapeai.app/",
        poll_interval_seconds=20.0,
        probe_timeout_seconds=3.0,
        public_timeout_seconds=5.0,
        connector_failure_threshold=3,
        connector_minimum_ready_connections=2,
        backoff_initial_seconds=5.0,
        backoff_max_seconds=120.0,
        event_log_max_bytes=65_536,
    )


def _store(settings: BridgeSettings) -> BridgeStateStore:
    return BridgeStateStore(
        status_path=settings.status_path,
        events_path=settings.events_path,
        maintenance_path=settings.maintenance_path,
        event_log_max_bytes=settings.event_log_max_bytes,
    )


class FakeProbes:
    def __init__(self) -> None:
        self.docker_result = ProbeResult(True, "ok")
        self.local_result = ProbeResult(True, "ok", "200")
        self.tunnel_result = ProbeResult(True, "ok")
        self.connector_result = ProbeResult(True, "ok", "200")
        self.public_result = ProbeResult(True, "ok", "302")

    def docker(self) -> ProbeResult:
        return self.docker_result

    def local_origin(self) -> ProbeResult:
        return self.local_result

    def tunnel(self) -> ProbeResult:
        return self.tunnel_result

    def connector(self) -> ProbeResult:
        return self.connector_result

    def public_origin(self) -> ProbeResult:
        return self.public_result


def _supervisor(
    tmp_path: Path,
    probes: FakeProbes,
    *,
    monotonic,
) -> BridgeSupervisor:
    settings = _settings(tmp_path)
    return BridgeSupervisor(
        settings=settings,
        state_store=_store(settings),
        probes=probes,
        supervisor_build_id="test-build",
        supervisor_pid=4242,
        monotonic=monotonic,
    )


def test_settings_project_exact_unix_docker_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/mindscape-docker.sock")

    settings = BridgeSettings.from_environment()

    assert settings.docker_socket_path == Path("/tmp/mindscape-docker.sock")


def test_launcher_uses_only_bounded_docker_desktop_socket_fallback(
) -> None:
    with tempfile.TemporaryDirectory(prefix="rwb-", dir="/tmp") as temporary:
        home = Path(temporary)
        docker_dir = home / ".docker/run"
        docker_dir.mkdir(parents=True)
        socket_path = docker_dir / "docker.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        try:
            environment = os.environ.copy()
            environment.pop("DOCKER_HOST", None)
            environment["HOME"] = str(home)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"source {REPO_ROOT / 'scripts/start_remote_workbench_tunnel.sh'}; printf %s \"$DOCKER_HOST\"",
                ],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            listener.close()

        assert result.stdout == f"unix://{socket_path}"


def test_tunnel_probe_reuses_one_bounded_docker_container_read_without_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    settings = _settings(tmp_path)
    payload = {
        "Name": f"/{settings.container_name}",
        "Image": f"sha256:{'a' * 64}",
        "State": {"Running": True},
        "HostConfig": {
            "RestartPolicy": {"Name": "unless-stopped"},
            "NetworkMode": settings.network_name,
            "PortBindings": {
                "2000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "2000"}]
            },
            "Privileged": False,
        },
        "Mounts": [{
            "Type": "bind",
            "Source": str(settings.token_path),
            "Destination": "/etc/cloudflared/tunnel-token",
            "RW": False,
        }],
        "Config": {
            "Image": settings.cloudflared_image,
            "Env": probes_module.CLOUDFLARED_CONTAINER_ENVIRONMENT,
            "User": probes_module.CLOUDFLARED_CONTAINER_USER,
            "Entrypoint": probes_module.CLOUDFLARED_ENTRYPOINT,
            "Cmd": probes_module.CLOUDFLARED_COMMAND,
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = (
        f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode()
        + body
    )

    class FakeSocket:
        def __init__(self, family: int, kind: int) -> None:
            observed["family"] = family
            observed["kind"] = kind
            observed["socket_calls"] = int(observed.get("socket_calls", 0)) + 1
            self.responses = [response, b""]

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def settimeout(self, timeout: float) -> None:
            observed["timeout"] = timeout

        def connect(self, path: str) -> None:
            observed["path"] = path

        def sendall(self, request: bytes) -> None:
            observed["request"] = request

        def recv(self, _limit: int) -> bytes:
            return self.responses.pop(0)

    monkeypatch.setattr(probes_module.socket, "socket", FakeSocket)
    probe = BridgeProbes(
        docker_socket_path=settings.docker_socket_path,
        container_name=settings.container_name,
        network_name=settings.network_name,
        token_path=settings.token_path,
        cloudflared_image=settings.cloudflared_image,
        metrics_host_port=settings.metrics_host_port,
        local_origin_url=settings.local_origin_url,
        connector_ready_url=settings.connector_ready_url,
        public_origin_url=settings.public_origin_url,
        probe_timeout_seconds=settings.probe_timeout_seconds,
        public_timeout_seconds=settings.public_timeout_seconds,
    )

    docker = probe.docker()
    tunnel = probe.tunnel()

    assert docker == ProbeResult(True, "ok")
    assert tunnel == ProbeResult(True, "ok")
    assert observed["socket_calls"] == 1
    assert observed["family"] == socket.AF_UNIX
    assert observed["path"] == str(settings.docker_socket_path)
    assert observed["request"] == (
        b"GET /containers/ig-workbench-cloudflared/json HTTP/1.1\r\n"
        b"Host: docker\r\nConnection: close\r\n\r\n"
    )
    assert not hasattr(probes_module, "subprocess")
    payload["Config"]["Image"] = "cloudflare/cloudflared:latest"
    probe._container_observation = (ProbeResult(True, "ok"), payload)
    assert probe.tunnel() == ProbeResult(False, "tunnel_contract_mismatch")


def test_docker_probe_decodes_bounded_chunked_ping_body() -> None:
    assert _decode_chunked_body(b"2\r\nOK\r\n0\r\n\r\n") == b"OK"


def test_http_probes_disable_environment_proxies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handlers: list[object] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    def build_opener(*values: object) -> Opener:
        handlers.extend(values)
        return Opener()

    monkeypatch.setattr(probes_module.urllib.request, "build_opener", build_opener)
    settings = _settings(tmp_path)
    probe = BridgeProbes(
        docker_socket_path=settings.docker_socket_path,
        container_name=settings.container_name,
        network_name=settings.network_name,
        token_path=settings.token_path,
        cloudflared_image=settings.cloudflared_image,
        metrics_host_port=settings.metrics_host_port,
        local_origin_url=settings.local_origin_url,
        connector_ready_url=settings.connector_ready_url,
        public_origin_url=settings.public_origin_url,
        probe_timeout_seconds=settings.probe_timeout_seconds,
        public_timeout_seconds=settings.public_timeout_seconds,
    )

    assert probe.local_origin() == ProbeResult(True, "ok", "200")
    assert any(isinstance(value, probes_module.urllib.request.ProxyHandler) for value in handlers)


def test_monotonic_gate_bounds_repeated_tunnel_repairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = FakeProbes()
    probes.tunnel_result = ProbeResult(False, "tunnel_not_running")
    now = [0.0]
    supervisor = _supervisor(tmp_path, probes, monotonic=lambda: now[0])
    repairs: list[str] = []
    monkeypatch.setattr(
        supervisor,
        "_launcher",
        lambda action: repairs.append(action) is None,
    )

    first = supervisor.run_once()
    second = supervisor.run_once()
    now[0] = 6.0
    third = supervisor.run_once()

    assert first["state"] == "recovering_tunnel"
    assert first["repair_action"] == "ensure"
    assert second["repair_action"] is None
    assert third["repair_action"] == "ensure"
    assert repairs == ["ensure", "ensure"]


def test_connector_degradation_is_distinct_before_bounded_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = FakeProbes()
    probes.connector_result = ProbeResult(False, "http_status", "503")
    supervisor = _supervisor(tmp_path, probes, monotonic=lambda: 100.0)
    repairs: list[str] = []
    monkeypatch.setattr(
        supervisor,
        "_launcher",
        lambda action: repairs.append(action) is None,
    )

    assert supervisor.run_once()["state"] == "degraded_tunnel"
    assert supervisor.run_once()["state"] == "degraded_tunnel"
    third = supervisor.run_once()

    assert third["state"] == "recovering_tunnel"
    assert third["repair_action"] == "restart"
    assert repairs == ["restart"]
    assert "degraded_tunnel" in KNOWN_STATES


def test_status_projection_only_accepts_activation_verifier_readback(
    tmp_path: Path,
) -> None:
    command = f"""
source {REPO_ROOT / 'scripts/start_remote_workbench_tunnel.sh'}
container_running() {{ return 0; }}
container_contract_valid() {{ return 0; }}
remote_ingress_live_json() {{ return 0; }}
token_file_valid() {{ return 0; }}
supervisor_activation_json() {{ printf '%s\n' '{{"activation_conformant":true,"maintenance":false,"ready":true,"state":"ready","status_fresh":true}}'; }}
status_json
"""
    environment = os.environ.copy()
    environment["REMOTE_WORKBENCH_BRIDGE_STATE_DIR"] = str(tmp_path / "state")
    result = subprocess.run(
        ["bash", "-c", command],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    projected = json.loads(result.stdout)

    assert projected["supervisor_activation_conformant"] is True
    assert projected["supervisor_fresh"] is True
    assert projected["supervisor_state"] == "ready"
    assert projected["ready"] is True


def test_origin_failure_never_repairs_the_tunnel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = FakeProbes()
    probes.local_result = ProbeResult(False, "http_status", "503")
    supervisor = _supervisor(tmp_path, probes, monotonic=lambda: 0.0)
    repairs: list[str] = []
    monkeypatch.setattr(
        supervisor,
        "_launcher",
        lambda action: repairs.append(action) is None,
    )

    status = supervisor.run_once()

    assert status["state"] == "degraded_origin"
    assert status["ready"] is False
    assert status["repair_action"] is None
    assert status["probes"]["local_origin"] == {
        "code": "http_status",
        "detail": "503",
        "ok": False,
    }
    assert "connector" not in status["probes"]
    assert "public_origin" not in status["probes"]
    assert repairs == []


def test_access_edge_failure_never_repairs_a_healthy_connector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = FakeProbes()
    probes.public_result = ProbeResult(False, "http_status", "503")
    supervisor = _supervisor(tmp_path, probes, monotonic=lambda: 0.0)
    repairs: list[str] = []
    monkeypatch.setattr(
        supervisor,
        "_launcher",
        lambda action: repairs.append(action) is None,
    )

    statuses = [supervisor.run_once() for _ in range(5)]

    assert {status["state"] for status in statuses} == {"degraded_remote"}
    assert all(status["ready"] is False for status in statuses)
    assert all(status["repair_action"] is None for status in statuses)
    assert all(status["probes"]["connector"]["ok"] is True for status in statuses)
    assert repairs == []


def test_transition_events_are_sanitized_and_name_previous_state(tmp_path: Path) -> None:
    probes = FakeProbes()
    supervisor = _supervisor(tmp_path, probes, monotonic=lambda: 0.0)
    supervisor.run_once()
    probes.public_result = ProbeResult(False, "http_status", "503")

    supervisor.run_once()

    events = [
        json.loads(line)
        for line in _settings(tmp_path).events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert set(events[-1]) == {
        "at",
        "previous_state",
        "ready",
        "repair_action",
        "state",
    }
    assert events[-1]["previous_state"] == "ready"
    assert events[-1]["state"] == "degraded_remote"
    assert "remote-workbench.mindscapeai.app" not in json.dumps(events[-1])


@pytest.mark.parametrize(("ready", "exit_code"), [(True, 0), (False, 2)])
def test_monitor_once_exit_code_tracks_composite_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ready: bool,
    exit_code: int,
) -> None:
    class StubSupervisor:
        def run_once(self) -> dict[str, object]:
            return {"ready": ready, "state": "ready" if ready else "degraded_remote"}

    class StubStore:
        def supervisor_lock(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return contextlib.nullcontext(True)

    monkeypatch.setattr(sys, "argv", ["remote_workbench_bridge_monitor.py", "--once"])
    monkeypatch.setattr(monitor_module, "source_build_id", lambda _root: "test-build")
    monkeypatch.setattr(
        monitor_module.BridgeSettings,
        "from_environment",
        lambda: _settings(tmp_path),
    )
    monkeypatch.setattr(
        monitor_module,
        "build_state_store",
        lambda _settings: StubStore(),
    )
    monkeypatch.setattr(
        monitor_module,
        "build_supervisor",
        lambda *_args, **_kwargs: StubSupervisor(),
    )

    assert monitor_module.main() == exit_code
    assert json.loads(capsys.readouterr().out)["ready"] is ready
