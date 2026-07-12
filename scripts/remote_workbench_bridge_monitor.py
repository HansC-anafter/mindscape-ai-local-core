#!/usr/bin/env python3
"""Run the host-side Remote Workbench bridge supervisor."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from remote_workbench_bridge import BridgeSettings, BridgeStateStore, BridgeSupervisor
from remote_workbench_bridge.activation import ActivationError, source_build_id
from remote_workbench_bridge.probes import BridgeProbes


def build_supervisor(
    settings: BridgeSettings,
    *,
    build_id: str,
    pid: int,
) -> BridgeSupervisor:
    """Build the supervisor with production probes and state storage."""

    store = BridgeStateStore(
        status_path=settings.status_path,
        events_path=settings.events_path,
        maintenance_path=settings.maintenance_path,
        event_log_max_bytes=settings.event_log_max_bytes,
    )
    probes = BridgeProbes(
        launcher_path=settings.launcher_path,
        local_origin_url=settings.local_origin_url,
        connector_ready_url=settings.connector_ready_url,
        public_origin_url=settings.public_origin_url,
        probe_timeout_seconds=settings.probe_timeout_seconds,
        public_timeout_seconds=settings.public_timeout_seconds,
    )
    return BridgeSupervisor(
        settings=settings,
        state_store=store,
        probes=probes,
        supervisor_build_id=build_id,
        supervisor_pid=pid,
    )


def main() -> int:
    """Run one probe cycle or the persistent supervisor loop."""

    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--once", action="store_true")
    actions.add_argument("--build-id", action="store_true")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    try:
        build_id = source_build_id(project_root)
    except ActivationError as error:
        parser.error(str(error))
    if args.build_id:
        print(build_id)
        return 0
    supervisor = build_supervisor(
        BridgeSettings.from_environment(),
        build_id=build_id,
        pid=os.getpid(),
    )
    if args.once:
        print(json.dumps(supervisor.run_once(), sort_keys=True))
        return 0
    supervisor.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
