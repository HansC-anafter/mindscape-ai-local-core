"""Supervise a bounded pool of independent one-slot runner workers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Mapping

from backend.app.runner.claim_start_delays import parse_claim_start_delays_ms


logger = logging.getLogger("backend.app.runner.worker_pool")
MAX_POOL_SIZE = 7
DEFAULT_SLOT_DELAYS_MS = "0,8000,16000,24000,32000,40000"
DEFAULT_SLOT_POLL_INTERVALS_MS = "250,350,450,550,650,750"


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _parse_pool_size(raw: str | None) -> int:
    try:
        value = int(raw or 6)
    except ValueError as exc:
        raise ValueError("invalid_runner_pool_size") from exc
    if value < 1 or value > MAX_POOL_SIZE:
        raise ValueError("runner_pool_size_out_of_range")
    return value


def _parse_poll_intervals_ms(raw: str | None) -> tuple[int, ...]:
    values = parse_claim_start_delays_ms(
        raw or DEFAULT_SLOT_POLL_INTERVALS_MS
    )
    if any(value < 100 for value in values):
        raise ValueError("runner_pool_poll_interval_too_small")
    return values


@dataclass(frozen=True)
class WorkerProcessSpec:
    name: str
    runner_id: str
    env: dict[str, str]

    @property
    def command(self) -> tuple[str, ...]:
        return (sys.executable, "-m", "backend.app.runner.worker")


def build_worker_process_specs(
    base_env: Mapping[str, str] | None = None,
) -> tuple[WorkerProcessSpec, ...]:
    source = dict(os.environ if base_env is None else base_env)
    pool_size = _parse_pool_size(source.get("LOCAL_CORE_RUNNER_POOL_SIZE"))
    slot_delays = parse_claim_start_delays_ms(
        source.get("LOCAL_CORE_RUNNER_POOL_SLOT_START_DELAYS_MS")
        or source.get("LOCAL_CORE_RUNNER_POST_CLAIM_START_DELAYS_MS")
        or DEFAULT_SLOT_DELAYS_MS
    )
    poll_intervals = _parse_poll_intervals_ms(
        source.get("LOCAL_CORE_RUNNER_POOL_POLL_INTERVALS_MS")
    )
    base_runner_id = (
        source.get("LOCAL_CORE_RUNNER_ID") or "default-browser-steady-six"
    ).strip()
    base_display_name = (
        source.get("LOCAL_CORE_RUNNER_DISPLAY_NAME")
        or "Default Local Browser Runner"
    ).strip()
    base_db_application_name = (
        source.get("DB_APPLICATION_NAME") or "local-core-runner-default-local-browser"
    ).strip()

    specs: list[WorkerProcessSpec] = []
    if _env_bool(
        source.get("LOCAL_CORE_RUNNER_POOL_MAINTENANCE_ENABLED"),
        True,
    ):
        runner_id = f"{base_runner_id}-maintenance"
        env = dict(source)
        env.update(
            {
                "LOCAL_CORE_RUNNER_ID": runner_id,
                "LOCAL_CORE_RUNNER_DISPLAY_NAME": f"{base_display_name} Maintenance",
                "LOCAL_CORE_RUNNER_MAX_INFLIGHT": "1",
                "LOCAL_CORE_RUNNER_MAINTENANCE_ONLY": "true",
                "LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED": "true",
                "LOCAL_CORE_RUNNER_POST_CLAIM_START_DELAYS_MS": "0",
                "LOCAL_CORE_RUNNER_POLL_INTERVAL_MS": "2000",
                "DB_APPLICATION_NAME": f"{base_db_application_name}-maintenance",
                "DB_POOL_SIZE": "2",
                "DB_MAX_OVERFLOW": "0",
            }
        )
        specs.append(
            WorkerProcessSpec(
                name="maintenance",
                runner_id=runner_id,
                env=env,
            )
        )

    for index in range(pool_size):
        slot_number = index + 1
        runner_id = f"{base_runner_id}-slot-{slot_number}"
        env = dict(source)
        env.update(
            {
                "LOCAL_CORE_RUNNER_ID": runner_id,
                "LOCAL_CORE_RUNNER_DISPLAY_NAME": (
                    f"{base_display_name} Slot {slot_number}"
                ),
                "LOCAL_CORE_RUNNER_MAX_INFLIGHT": "1",
                "LOCAL_CORE_RUNNER_MAINTENANCE_ONLY": "false",
                "LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED": "false",
                "LOCAL_CORE_RUNNER_POST_CLAIM_START_DELAYS_MS": str(
                    slot_delays[index % len(slot_delays)]
                ),
                "LOCAL_CORE_RUNNER_POLL_INTERVAL_MS": str(
                    poll_intervals[index % len(poll_intervals)]
                ),
                "LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS": "20",
                "DB_APPLICATION_NAME": (
                    f"{base_db_application_name}-slot-{slot_number}"
                ),
                "DB_POOL_SIZE": "2",
                "DB_MAX_OVERFLOW": "0",
            }
        )
        specs.append(
            WorkerProcessSpec(
                name=f"slot-{slot_number}",
                runner_id=runner_id,
                env=env,
            )
        )

    return tuple(specs)


class WorkerPoolSupervisor:
    def __init__(self, specs: tuple[WorkerProcessSpec, ...]):
        self.specs = specs
        self.processes: dict[str, subprocess.Popen] = {}
        self.restart_after: dict[str, float] = {}
        self.stopping = False

    def request_stop(self, _signum=None, _frame=None) -> None:
        self.stopping = True

    def _spawn(self, spec: WorkerProcessSpec) -> None:
        process = subprocess.Popen(spec.command, env=spec.env)
        self.processes[spec.name] = process
        logger.info(
            "Runner pool child started name=%s runner_id=%s pid=%s",
            spec.name,
            spec.runner_id,
            process.pid,
        )

    def _stop_children(self) -> None:
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if all(process.poll() is not None for process in self.processes.values()):
                return
            time.sleep(0.2)
        for process in self.processes.values():
            if process.poll() is None:
                process.kill()

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        restart_backoff = max(
            1,
            int(os.getenv("LOCAL_CORE_RUNNER_POOL_RESTART_BACKOFF_SECONDS", "2")),
        )
        try:
            while not self.stopping:
                now = time.monotonic()
                for spec in self.specs:
                    process = self.processes.get(spec.name)
                    if process is None:
                        if now >= self.restart_after.get(spec.name, 0):
                            self._spawn(spec)
                        continue
                    return_code = process.poll()
                    if return_code is None:
                        continue
                    logger.error(
                        "Runner pool child exited name=%s runner_id=%s return_code=%s",
                        spec.name,
                        spec.runner_id,
                        return_code,
                    )
                    self.processes.pop(spec.name, None)
                    self.restart_after[spec.name] = now + restart_backoff
                time.sleep(0.25)
        finally:
            self._stop_children()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    specs = build_worker_process_specs()
    logger.info(
        "Runner pool supervisor starting children=%s runner_ids=%s",
        len(specs),
        ",".join(spec.runner_id for spec in specs),
    )
    WorkerPoolSupervisor(specs).run_forever()


if __name__ == "__main__":
    main()
