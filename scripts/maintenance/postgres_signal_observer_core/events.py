"""Parse filtered signal_generate records without retaining raw trace lines."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_PREFIX_PATTERN = re.compile(
    r"^\s*(?P<sender_comm>.+?)-(?P<sender_pid>\d+)"
    r"(?:\s+\(\s*\d+\))?\s+\[\d+\].*?"
    r"(?P<monotonic_seconds>\d+\.\d+):\s+signal_generate:\s*(?P<payload>.*)$"
)
_FIELD_PATTERN = re.compile(r"(?P<key>[a-z_]+)=(?P<value>\"[^\"]*\"|\S+)")


@dataclass(frozen=True)
class SignalGenerateEvent:
    sender_comm: str
    sender_host_pid: int
    target_comm: str
    target_host_pid: int
    signal: int
    signal_errno: int
    signal_code: int
    signal_group: int
    signal_result: int
    monotonic_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_signal_generate_line(line: str) -> SignalGenerateEvent | None:
    """Return one exact SIGQUIT-to-postgres event or None for unrelated lines."""

    raw = str(line or "").strip("\n")
    if "signal_generate:" not in raw:
        return None
    match = _PREFIX_PATTERN.match(raw)
    if not match:
        raise ValueError("signal_generate_trace_line_invalid")
    fields = {
        item.group("key"): item.group("value").strip('"')
        for item in _FIELD_PATTERN.finditer(match.group("payload"))
    }
    required = {"sig", "errno", "code", "comm", "pid", "group", "result"}
    if not required.issubset(fields):
        raise ValueError("signal_generate_trace_fields_missing")
    try:
        event = SignalGenerateEvent(
            sender_comm=match.group("sender_comm").strip(),
            sender_host_pid=int(match.group("sender_pid")),
            target_comm=fields["comm"],
            target_host_pid=int(fields["pid"]),
            signal=int(fields["sig"]),
            signal_errno=int(fields["errno"]),
            signal_code=int(fields["code"]),
            signal_group=int(fields["group"]),
            signal_result=int(fields["result"]),
            monotonic_seconds=float(match.group("monotonic_seconds")),
        )
    except ValueError as exc:
        raise ValueError("signal_generate_trace_fields_invalid") from exc
    if event.signal != 3 or event.target_comm != "postgres":
        return None
    return event


def read_namespace_pids(
    host_pid: int, *, proc_root: Path = Path("/proc")
) -> tuple[int, ...]:
    """Read the kernel-provided host-to-container PID chain for one process."""

    if int(host_pid) <= 0:
        raise ValueError("host_pid_must_be_positive")
    status_path = proc_root / str(int(host_pid)) / "status"
    try:
        lines = status_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise RuntimeError("process_namespace_status_unavailable") from exc
    for line in lines:
        if not line.startswith("NSpid:"):
            continue
        try:
            values = tuple(int(value) for value in line.split(":", 1)[1].split())
        except ValueError as exc:
            raise RuntimeError("process_namespace_pid_invalid") from exc
        if not values:
            break
        return values
    raise RuntimeError("process_namespace_pid_unavailable")
