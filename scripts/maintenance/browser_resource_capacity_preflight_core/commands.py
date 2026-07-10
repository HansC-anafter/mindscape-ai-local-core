"""Read-only command enforcement for browser capacity evidence collection."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Sequence


_DOCKER_READ_ACTIONS = {"exec", "info", "inspect", "ps", "stats", "top"}
_DOCKER_MUTATIONS = {
    "compose",
    "cp",
    "create",
    "kill",
    "pause",
    "restart",
    "rm",
    "run",
    "start",
    "stop",
    "unpause",
    "update",
}
_INNER_READ_BINARIES = {"cat", "env", "psql", "python", "redis-cli"}
_SQL_MUTATION = re.compile(
    r"\b(alter|call|copy|create|delete|do|drop|grant|insert|revoke|truncate|update)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def _validate_psql(argv: Sequence[str]) -> None:
    try:
        sql = argv[argv.index("-Atc") + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("psql requires one -Atc read query") from exc
    stripped = sql.lstrip().lower()
    if not stripped.startswith(("select", "show", "with")):
        raise ValueError("psql query must start with SELECT, SHOW, or WITH")
    if _SQL_MUTATION.search(sql):
        raise ValueError("psql mutation is forbidden")


def ensure_read_only_command(argv: Sequence[str]) -> None:
    """Reject commands outside the preflight's bounded read-only surface."""

    if len(argv) < 2 or argv[0] != "docker":
        raise ValueError("only docker read commands are allowed")
    action = argv[1]
    if action in _DOCKER_MUTATIONS or action not in _DOCKER_READ_ACTIONS:
        raise ValueError(f"docker action is forbidden: {action}")
    if action != "exec":
        return
    if len(argv) < 4:
        raise ValueError("docker exec requires a container and command")
    inner = argv[3]
    if inner not in _INNER_READ_BINARIES:
        raise ValueError(f"docker exec command is forbidden: {inner}")
    if inner == "psql":
        _validate_psql(argv[3:])
    if inner == "redis-cli":
        upper = {part.upper() for part in argv[4:]}
        if upper.isdisjoint({"GET", "TTL", "EVAL_RO"}):
            raise ValueError("redis-cli requires GET, TTL, or EVAL_RO")
        if upper.intersection({"DEL", "EVAL", "FLUSHALL", "FLUSHDB", "SET"}):
            raise ValueError("Redis mutation is forbidden")


class ReadOnlyCommandRunner:
    """Execute only commands accepted by the read-only policy."""

    def run(self, argv: Sequence[str], *, timeout_seconds: int = 5) -> CommandResult:
        ensure_read_only_command(argv)
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
        return CommandResult(
            argv=tuple(argv),
            returncode=int(completed.returncode),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
