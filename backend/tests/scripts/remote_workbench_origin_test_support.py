from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.origin import LOCKED_HOST_BINDINGS


def service_ports(bindings: dict[tuple[int, str], int]) -> dict:
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


def locked_config() -> dict:
    return {
        "name": "mindscape-ai-local-core",
        "services": {
            name: service_ports(bindings)
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
                    "totals": {
                        "pending": 0,
                        "processing": 0,
                        "delayed": 0,
                        "deadletter": 0,
                    },
                    "inventory": [],
                    "runners": {
                        "count": 1,
                        "capacity": 2,
                        "inflight": 0,
                        "malformed": 0,
                    },
                }
            )
        return ""
