"""Configuration for the host-side Remote Workbench bridge supervisor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class BridgeSettings:
    """Bounded settings used by the bridge supervisor."""

    project_root: Path
    state_dir: Path
    launcher_path: Path
    status_path: Path
    events_path: Path
    maintenance_path: Path
    docker_socket_path: Path
    container_name: str
    network_name: str
    internal_target: str
    local_origin_url: str
    connector_ready_url: str
    public_origin_url: str
    poll_interval_seconds: float
    probe_timeout_seconds: float
    public_timeout_seconds: float
    connector_failure_threshold: int
    backoff_initial_seconds: float
    backoff_max_seconds: float
    event_log_max_bytes: int

    @classmethod
    def from_environment(cls) -> "BridgeSettings":
        """Load settings from environment variables with bounded defaults."""

        project_root = Path(
            os.getenv(
                "REMOTE_WORKBENCH_PROJECT_ROOT",
                str(Path(__file__).resolve().parents[2]),
            )
        ).expanduser().resolve()
        state_dir = Path(
            os.getenv(
                "REMOTE_WORKBENCH_BRIDGE_STATE_DIR",
                "~/.mindscape/remote-workbench-bridge",
            )
        ).expanduser().resolve()
        docker_host = os.getenv("DOCKER_HOST", "")
        docker_socket_path = (
            Path(docker_host.removeprefix("unix://")).expanduser()
            if docker_host.startswith("unix://")
            else Path.home() / ".docker" / "run" / "docker.sock"
        )
        return cls(
            project_root=project_root,
            state_dir=state_dir,
            launcher_path=project_root / "scripts/start_remote_workbench_tunnel.sh",
            status_path=state_dir / "status.json",
            events_path=state_dir / "events.jsonl",
            maintenance_path=state_dir / "maintenance.json",
            docker_socket_path=docker_socket_path,
            container_name=os.getenv(
                "REMOTE_WORKBENCH_TUNNEL_CONTAINER",
                "ig-workbench-cloudflared",
            ),
            network_name="mindscape-network",
            internal_target="http://mindscape-ai-local-core-frontend:3001",
            local_origin_url=os.getenv(
                "REMOTE_WORKBENCH_LOCAL_ORIGIN_URL",
                "http://127.0.0.1:8300/healthz",
            ),
            connector_ready_url=os.getenv(
                "REMOTE_WORKBENCH_CONNECTOR_READY_URL",
                "http://127.0.0.1:2000/ready",
            ),
            public_origin_url=os.getenv(
                "REMOTE_WORKBENCH_PUBLIC_ORIGIN_URL",
                "https://remote-workbench.mindscapeai.app/",
            ),
            poll_interval_seconds=_bounded_float(
                "REMOTE_WORKBENCH_BRIDGE_POLL_SECONDS", 20.0, 5.0, 300.0
            ),
            probe_timeout_seconds=_bounded_float(
                "REMOTE_WORKBENCH_BRIDGE_PROBE_TIMEOUT_SECONDS", 3.0, 0.5, 15.0
            ),
            public_timeout_seconds=_bounded_float(
                "REMOTE_WORKBENCH_BRIDGE_PUBLIC_TIMEOUT_SECONDS", 5.0, 1.0, 20.0
            ),
            connector_failure_threshold=_bounded_int(
                "REMOTE_WORKBENCH_CONNECTOR_FAILURE_THRESHOLD", 3, 2, 10
            ),
            backoff_initial_seconds=_bounded_float(
                "REMOTE_WORKBENCH_BRIDGE_BACKOFF_INITIAL_SECONDS", 5.0, 1.0, 60.0
            ),
            backoff_max_seconds=_bounded_float(
                "REMOTE_WORKBENCH_BRIDGE_BACKOFF_MAX_SECONDS", 120.0, 10.0, 600.0
            ),
            event_log_max_bytes=_bounded_int(
                "REMOTE_WORKBENCH_BRIDGE_EVENT_LOG_MAX_BYTES",
                524_288,
                65_536,
                4_194_304,
            ),
        )
