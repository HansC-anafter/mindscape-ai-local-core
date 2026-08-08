"""Configuration for the host-side Remote Workbench bridge supervisor."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path


CLOUDFLARED_IMAGE = (
    "cloudflare/cloudflared@sha256:"
    "ba461b8aa9c042156dbd39c38657fe7431bafa063220eab8d5330a523863da9f"
)


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if not math.isfinite(value) or value < minimum or value > maximum:
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
    token_path: Path
    cloudflared_image: str
    metrics_host_port: int
    local_origin_url: str
    control_plane_health_url: str
    connector_ready_url: str
    public_origin_url: str
    poll_interval_seconds: float
    probe_timeout_seconds: float
    public_timeout_seconds: float
    origin_failure_threshold: int
    connector_failure_threshold: int
    connector_minimum_ready_connections: int
    backoff_initial_seconds: float
    backoff_max_seconds: float
    event_log_max_bytes: int

    @property
    def lock_path(self) -> Path:
        """Return the single-instance supervisor lock path."""

        return self.state_dir / "supervisor.lock"

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
            token_path=Path(
                os.getenv(
                    "REMOTE_WORKBENCH_CLOUDFLARED_TOKEN_FILE",
                    str(project_root / "data/cloudflared/tunnel-token"),
                )
            ).expanduser().resolve(),
            cloudflared_image=CLOUDFLARED_IMAGE,
            metrics_host_port=2000,
            local_origin_url=os.getenv(
                "REMOTE_WORKBENCH_LOCAL_ORIGIN_URL",
                "http://127.0.0.1:8300/api/v1/host/services/mobile-workbench-gateway/health",
            ),
            control_plane_health_url=os.getenv(
                "REMOTE_WORKBENCH_CONTROL_PLANE_HEALTH_URL",
                "http://127.0.0.1:8220/healthz",
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
            origin_failure_threshold=_bounded_int(
                "REMOTE_WORKBENCH_ORIGIN_FAILURE_THRESHOLD", 2, 2, 10
            ),
            connector_failure_threshold=_bounded_int(
                "REMOTE_WORKBENCH_CONNECTOR_FAILURE_THRESHOLD", 3, 2, 10
            ),
            connector_minimum_ready_connections=_bounded_int(
                "REMOTE_WORKBENCH_BRIDGE_MINIMUM_READY_CONNECTIONS", 2, 1, 4
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
