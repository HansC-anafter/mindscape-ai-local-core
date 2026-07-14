#!/usr/bin/env python3
"""Run the host-side Remote Workbench bridge supervisor."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from remote_workbench_bridge import BridgeSettings, BridgeStateStore, BridgeSupervisor
from remote_workbench_bridge.activation import ActivationError, source_build_id
from remote_workbench_bridge.probes import BridgeProbes


STATUS_OUTPUT_LIMIT_BYTES = 65_536


def build_state_store(settings: BridgeSettings) -> BridgeStateStore:
    """Build the secure file-backed supervisor state store."""

    return BridgeStateStore(
        status_path=settings.status_path,
        events_path=settings.events_path,
        maintenance_path=settings.maintenance_path,
        event_log_max_bytes=settings.event_log_max_bytes,
    )


def build_supervisor(
    settings: BridgeSettings,
    *,
    build_id: str,
    pid: int,
    state_store: BridgeStateStore | None = None,
) -> BridgeSupervisor:
    """Build the supervisor with production probes and state storage."""

    store = state_store or build_state_store(settings)
    probes = BridgeProbes(
        launcher_path=settings.launcher_path,
        docker_socket_path=settings.docker_socket_path,
        local_origin_url=settings.local_origin_url,
        connector_ready_url=settings.connector_ready_url,
        public_origin_url=settings.public_origin_url,
        probe_timeout_seconds=settings.probe_timeout_seconds,
        public_timeout_seconds=settings.public_timeout_seconds,
        connector_minimum_ready_connections=(
            settings.connector_minimum_ready_connections
        ),
    )
    return BridgeSupervisor(
        settings=settings,
        state_store=store,
        probes=probes,
        supervisor_build_id=build_id,
        supervisor_pid=pid,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("run", "once", "status"))
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--once", action="store_true")
    actions.add_argument("--build-id", action="store_true")
    parser.add_argument("--no-repair", action="store_true")
    return parser


def _resolve_mode(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    if args.build_id:
        if args.command is not None or args.no_repair:
            parser.error("--build-id accepts no command or repair option")
        return "build-id"
    if args.once:
        if args.command not in (None, "once"):
            parser.error("--once cannot select another command")
        return "once"
    mode = args.command or "run"
    if mode == "status" and args.no_repair:
        parser.error("status does not accept --no-repair")
    return mode


def _print_launcher_status(settings: BridgeSettings) -> int:
    """Delegate status projection to the one canonical tunnel launcher."""

    try:
        result = subprocess.run(
            [str(settings.launcher_path), "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.probe_timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        print(json.dumps({"ready": False, "state": "launcher_unavailable"}))
        return 1
    if len(result.stdout.encode("utf-8")) > STATUS_OUTPUT_LIMIT_BYTES:
        print(json.dumps({"ready": False, "state": "launcher_status_oversized"}))
        return 1
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"ready": False, "state": "launcher_status_malformed"}
    if not isinstance(payload, dict):
        payload = {"ready": False, "state": "launcher_status_malformed"}
    print(json.dumps(payload, sort_keys=True))
    if result.returncode != 0:
        return 1
    return 0 if payload.get("ready") is True else 2


def main() -> int:
    """Run one probe cycle or the persistent supervisor loop."""

    parser = _parser()
    args = parser.parse_args()
    mode = _resolve_mode(parser, args)
    project_root = Path(__file__).resolve().parents[1]
    try:
        build_id = source_build_id(project_root)
    except ActivationError as error:
        parser.error(str(error))
    if mode == "build-id":
        print(build_id)
        return 0
    settings = BridgeSettings.from_environment()
    if mode == "status":
        return _print_launcher_status(settings)
    if mode == "once":
        supervisor = build_supervisor(
            settings,
            build_id=build_id,
            pid=os.getpid(),
        )
        status = (
            supervisor.run_once(repair=False)
            if args.no_repair
            else supervisor.run_once()
        )
        print(json.dumps(status, sort_keys=True))
        return 0 if status.get("ready") is True else 2
    state_store = build_state_store(settings)
    supervisor = build_supervisor(
        settings,
        build_id=build_id,
        pid=os.getpid(),
        state_store=state_store,
    )
    signal.signal(signal.SIGTERM, supervisor.request_stop)
    signal.signal(signal.SIGINT, supervisor.request_stop)
    with state_store.supervisor_lock(settings.lock_path, pid=os.getpid()) as acquired:
        if not acquired:
            print("Remote Workbench bridge supervisor is already running.", file=sys.stderr)
            return 0
        if args.no_repair:
            supervisor.run_forever(repair=False)
        else:
            supervisor.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
