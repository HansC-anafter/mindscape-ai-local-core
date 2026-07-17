"""Immutable bounded evidence and fail-closed observer health receipts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EvidenceBudget:
    max_events: int = 64
    max_event_bytes: int = 65_536
    max_total_bytes: int = 4_194_304

    def validate(self) -> None:
        if self.max_events != 64:
            raise ValueError("observer_max_events_must_equal_64")
        if self.max_event_bytes != 65_536:
            raise ValueError("observer_max_event_bytes_must_equal_65536")
        if self.max_total_bytes != 4_194_304:
            raise ValueError("observer_max_total_bytes_must_equal_4194304")

    def sha256(self) -> str:
        self.validate()
        payload = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class EvidenceCapacityExhausted(RuntimeError):
    """Raised before any existing evidence can be overwritten."""


class ObserverEvidenceStore:
    """Write at most 64 immutable, individually hashed signal receipts."""

    def __init__(self, root: Path, *, budget: EvidenceBudget | None = None) -> None:
        self.root = Path(root)
        self.events_root = self.root / "events"
        self.health_path = self.root / "health.json"
        self.lock_path = self.root / ".observer.lock"
        self.budget = budget or EvidenceBudget()
        self.budget.validate()

    def _ensure_root(self) -> None:
        self.events_root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._ensure_root()
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def usage(self) -> dict[str, int]:
        self._ensure_root()
        event_paths = sorted(self.events_root.glob("event-*.json"))
        return {
            "event_count": len(event_paths),
            "total_event_bytes": sum(path.stat().st_size for path in event_paths),
        }

    def append_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        serialized = (
            json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        if len(serialized) > self.budget.max_event_bytes:
            raise EvidenceCapacityExhausted("observer_event_byte_budget_exhausted")
        digest = hashlib.sha256(serialized).hexdigest()
        with self._lock():
            usage = self.usage()
            if usage["event_count"] >= self.budget.max_events:
                raise EvidenceCapacityExhausted("observer_event_count_budget_exhausted")
            if (
                usage["total_event_bytes"] + len(serialized)
                > self.budget.max_total_bytes
            ):
                raise EvidenceCapacityExhausted("observer_total_byte_budget_exhausted")
            event_index = usage["event_count"] + 1
            event_path = (
                self.events_root / f"event-{event_index:03d}-{digest[:16]}.json"
            )
            try:
                with event_path.open("xb") as event_file:
                    event_file.write(serialized)
                    event_file.flush()
                    os.fsync(event_file.fileno())
                directory_fd = os.open(self.events_root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except FileExistsError as exc:
                raise RuntimeError("observer_event_path_collision") from exc
        return {
            "event_index": event_index,
            "event_path": str(event_path),
            "event_sha256": digest,
            "event_bytes": len(serialized),
        }

    def write_health(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        usage = self.usage()
        health = {
            **dict(payload),
            "updated_at": utc_now(),
            "budget": asdict(self.budget),
            "budget_sha256": self.budget.sha256(),
            **usage,
        }
        self._ensure_root()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.root,
            prefix=".health-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(health, temporary, sort_keys=True, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, self.health_path)
        return health

    def read_health(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.health_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("observer_health_unavailable") from exc
        return dict(payload)
