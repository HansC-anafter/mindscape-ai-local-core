"""Compatibility tests for the secure Remote Workbench bridge seam."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import remote_workbench_bridge.probes as probes_module
import remote_workbench_bridge.supervisor as supervisor_module
import remote_workbench_bridge_monitor as monitor_module
from remote_workbench_bridge.probes import BridgeProbes, ProbeResult
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


def _probes(settings: BridgeSettings) -> BridgeProbes:
    return BridgeProbes(
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
        connector_minimum_ready_connections=(
            settings.connector_minimum_ready_connections
        ),
    )


class _FakeProbes:
    def __init__(self) -> None:
        self.tunnel_result = ProbeResult(True, "ok")

    def docker(self) -> ProbeResult:
        return ProbeResult(True, "ok")

    def local_origin(self) -> ProbeResult:
        return ProbeResult(True, "ok", "200")

    def tunnel(self) -> ProbeResult:
        return self.tunnel_result

    def connector(self) -> ProbeResult:
        return ProbeResult(True, "ok", "200", 2)

    def public_origin(self) -> ProbeResult:
        return ProbeResult(True, "ok", "302")


def _supervisor(
    settings: BridgeSettings,
    probes: _FakeProbes,
    *,
    sleep: Callable[[float], None] | None = None,
) -> BridgeSupervisor:
    return BridgeSupervisor(
        settings=settings,
        state_store=_store(settings),
        probes=probes,
        supervisor_build_id="test-build",
        supervisor_pid=4242,
        sleep=sleep or (lambda _seconds: None),
        monotonic=lambda: 0.0,
    )


def test_connector_capacity_uses_one_bounded_request_with_fixed_user_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {"calls": 0}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            observed["limit"] = limit
            return b'{"readyConnections":1}'

    class Opener:
        def open(self, request, **_kwargs: object) -> Response:  # noqa: ANN001
            observed["calls"] = int(observed["calls"]) + 1
            observed["user_agent"] = request.get_header("User-agent")
            return Response()

    monkeypatch.setattr(
        probes_module.urllib.request,
        "build_opener",
        lambda *_handlers: Opener(),
    )
    settings = _settings(tmp_path)
    probe = _probes(settings)

    result = probe.connector()

    assert result == ProbeResult(False, "connector_capacity", "200", 1)
    assert observed == {
        "calls": 1,
        "limit": probes_module.CONNECTOR_RESPONSE_LIMIT_BYTES + 1,
        "user_agent": probes_module.BRIDGE_USER_AGENT,
    }


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        b"{}",
        b"[]",
        b'{"readyConnections":true}',
        b'{"readyConnections":-1}',
        b'{"readyConnections":"2"}',
        b'{"readyConnections":' + (b"9" * 5000) + b"}",
    ],
)
def test_connector_malformed_payloads_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    probe = _probes(_settings(tmp_path))
    monkeypatch.setattr(
        probe,
        "_http_response",
        lambda *_args, **_kwargs: (ProbeResult(True, "ok", "200"), body),
    )

    assert probe.connector().code == "connector_readiness_malformed"


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_bridge_settings_reject_non_finite_polling_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("REMOTE_WORKBENCH_BRIDGE_POLL_SECONDS", value)
    with pytest.raises(ValueError, match="must be between"):
        BridgeSettings.from_environment()


def test_no_repair_mode_preserves_degraded_state_without_launcher_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    probes = _FakeProbes()
    probes.tunnel_result = ProbeResult(False, "tunnel_not_running")
    supervisor = _supervisor(settings, probes)
    repairs: list[str] = []
    monkeypatch.setattr(
        supervisor,
        "_launcher",
        lambda action: repairs.append(action) is None,
    )

    status = supervisor.run_once(repair=False)

    assert status["state"] == "recovering_tunnel"
    assert status["repair_action"] is None
    assert repairs == []


def test_launcher_timeout_kills_the_complete_independent_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    real_popen = supervisor_module.subprocess.Popen
    launcher_body = tmp_path / "leader-exits-child-ignores-term.sh"
    launcher_body.write_text(
        "trap 'exit 0' TERM\n"
        "( trap '' TERM; sleep 30 ) &\n"
        "wait\n",
        encoding="utf-8",
    )

    def recording_popen(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        process = real_popen(*args, **kwargs)
        observed.update({"process": process, "kwargs": kwargs})
        return process

    monkeypatch.setattr(supervisor_module.subprocess, "Popen", recording_popen)
    settings = replace(_settings(tmp_path), launcher_path=Path("/bin/sh"))
    supervisor = _supervisor(settings, _FakeProbes())
    monkeypatch.setattr(supervisor_module, "LAUNCHER_DEADLINE_SECONDS", 0.1)
    monkeypatch.setattr(supervisor_module, "LAUNCHER_TERMINATE_GRACE_SECONDS", 0.1)
    monkeypatch.setattr(supervisor_module, "LAUNCHER_KILL_GRACE_SECONDS", 1.0)

    assert supervisor._launcher(str(launcher_body)) is False
    process = observed["process"]
    assert observed["kwargs"]["start_new_session"] is True
    assert process.poll() is not None
    try:
        with pytest.raises(ProcessLookupError):
            os.killpg(process.pid, 0)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_stubborn_launcher_escalates_from_term_to_kill_after_sixty_seconds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    signals: list[int] = []
    options: dict[str, object] = {}
    group_alive = {"value": True}

    class StubbornProcess:
        pid = 424242

        def wait(self, *, timeout: float) -> int:
            waits.append(timeout)
            if len(waits) < 3:
                raise subprocess.TimeoutExpired("launcher", timeout)
            return -signal.SIGKILL

    def popen(_args, **kwargs):  # noqa: ANN001, ANN202
        options.update(kwargs)
        return StubbornProcess()

    def killpg(_pid: int, signum: int) -> None:
        if signum == 0:
            if group_alive["value"]:
                return
            raise ProcessLookupError
        signals.append(signum)
        if signum == signal.SIGKILL:
            group_alive["value"] = False

    monkeypatch.setattr(supervisor_module.subprocess, "Popen", popen)
    monkeypatch.setattr(supervisor_module.os, "killpg", killpg)

    assert _supervisor(_settings(tmp_path), _FakeProbes())._launcher("restart") is False
    assert waits[0] >= 60.0
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert options["start_new_session"] is True


def test_supervisor_lock_is_private_and_non_blocking(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = _store(settings)

    with store.supervisor_lock(settings.lock_path, pid=4242) as acquired:
        assert acquired is True
        assert settings.lock_path.read_text(encoding="utf-8") == "4242\n"
        assert settings.lock_path.stat().st_mode & 0o777 == 0o600
        with store.supervisor_lock(settings.lock_path, pid=4343) as second:
            assert second is False


@pytest.mark.parametrize("once", [True, False])
def test_run_and_once_fail_closed_before_building_or_writing_when_lock_is_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    once: bool,
) -> None:
    settings = _settings(tmp_path)
    store = _store(settings)
    builds: list[bool] = []
    monkeypatch.setattr(monitor_module, "build_state_store", lambda _settings: store)
    monkeypatch.setattr(
        monitor_module,
        "build_supervisor",
        lambda *_args, **_kwargs: builds.append(True),
    )

    with store.supervisor_lock(settings.lock_path, pid=4242) as acquired:
        assert acquired is True
        result = monitor_module._run_locked_supervisor(
            settings, build_id="test-build", once=once, repair=True
        )

    assert result == 3
    assert builds == []
    assert not settings.status_path.exists()
    assert not settings.events_path.exists()


def test_stop_request_ends_the_bounded_supervisor_loop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    probes = _FakeProbes()
    supervisor: BridgeSupervisor

    def stop_after_first_interval(_seconds: float) -> None:
        supervisor.request_stop()

    supervisor = _supervisor(settings, probes, sleep=stop_after_first_interval)

    supervisor.run_forever(repair=False)

    assert supervisor.stop_requested is True
    assert settings.status_path.is_file()


def _run_recreate_shell(
    tmp_path: Path, failed_dependency: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    events = tmp_path / "docker-events"
    command = f"""
source {json.dumps(str(REPO_ROOT / 'scripts/start_remote_workbench_tunnel.sh'))}
ensure_state_dir() {{ :; }}
stop_tunnel() {{ :; }}
token_file_valid() {{ [[ "$FAIL_AT" != token ]]; }}
remote_ingress_lock_valid() {{ [[ "$FAIL_AT" != lock ]]; }}
container_exists() {{ return 0; }}
wait_remote_ingress_live() {{ return 0; }}
docker() {{
  printf '%s\n' "$*" >> "$EVENTS"
  if [[ "$FAIL_AT:${{1:-}}:${{2:-}}" == network:network:inspect || "$FAIL_AT:${{1:-}}:${{2:-}}" == image:image:inspect ]]; then
    return 1
  fi
  return 0
}}
recreate_tunnel
"""
    environment = os.environ.copy()
    environment.update({"EVENTS": str(events), "FAIL_AT": failed_dependency})
    result = subprocess.run(
        ["bash", "-c", command],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = events.read_text(encoding="utf-8").splitlines() if events.exists() else []
    return result, lines


@pytest.mark.parametrize("failed_dependency", ["token", "lock", "network", "image"])
def test_recreate_dependency_failure_never_removes_or_creates(
    tmp_path: Path, failed_dependency: str
) -> None:
    result, events = _run_recreate_shell(tmp_path, failed_dependency)

    assert result.returncode != 0
    assert not any(event.startswith(("rm ", "run ")) for event in events)


def test_recreate_preflights_dependencies_before_remove_and_never_pulls(
    tmp_path: Path,
) -> None:
    result, events = _run_recreate_shell(tmp_path, "none")

    assert result.returncode == 0, result.stderr
    assert events[0] == "network inspect mindscape-network"
    assert events[1].startswith("image inspect cloudflare/cloudflared@sha256:")
    assert events[2] == "rm -f ig-workbench-cloudflared"
    assert events[3].startswith("run -d --pull=never --name ig-workbench-cloudflared")
    launcher = (REPO_ROOT / "scripts/start_remote_workbench_tunnel.sh").read_text()
    assert "file_mtime" not in launcher
    assert "grep -Fq" not in launcher


def test_launcher_legacy_flags_normalize_into_the_secure_canonical_actions() -> None:
    command = f"""
source {REPO_ROOT / 'scripts/start_remote_workbench_tunnel.sh'}
ensure_tunnel() {{ printf 'ensure\n'; }}
restart_tunnel() {{ printf 'restart\n'; }}
recreate_tunnel() {{ printf 'recreate\n'; }}
main
main --restart
main --recreate
"""

    result = subprocess.run(
        ["bash", "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["ensure", "restart", "recreate"]


def test_monitor_status_delegates_to_the_canonical_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    observed: dict[str, object] = {}

    def run(args, **kwargs):  # noqa: ANN001
        observed["args"] = args
        observed["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout='{"ready":true,"state":"ready"}\n',
            stderr="",
        )

    monkeypatch.setattr(monitor_module.subprocess, "run", run)

    assert monitor_module._print_launcher_status(settings) == 0
    assert observed == {
        "args": [str(settings.launcher_path), "status", "--json"],
        "timeout": settings.probe_timeout_seconds,
    }
    assert json.loads(capsys.readouterr().out) == {
        "ready": True,
        "state": "ready",
    }


def test_installer_retries_bootstrap_without_system_python_fallback() -> None:
    installer = (
        REPO_ROOT / "scripts/install-remote-workbench-bridge-macos.sh"
    ).read_text(encoding="utf-8")
    maintenance = installer.index(
        '"$LAUNCHER" maintenance enter supervisor_activation'
    )
    bootstrap = installer.index('"$LAUNCHCTL_BIN" bootstrap')

    assert maintenance < bootstrap
    assert "for attempt in 1 2 3" in installer[maintenance:]
    assert "Supervisor bootstrap failed after three attempts" in installer
    assert "/usr/bin/python3" not in installer
    assert "command -v python3" not in installer
