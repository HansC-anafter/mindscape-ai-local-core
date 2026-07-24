"""Immutable bounded evidence and fail-closed observer health receipts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
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
        self.signal_target_path = self.root / "signal-target.json"
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

    def write_signal_target(
        self,
        *,
        postgres_pid: int,
        host_pid: int,
        correlation: Mapping[str, Any] | None = None,
    ) -> None:
        """Publish one bounded target mapping before the synthetic signal."""

        if not all(
            type(value) is int and 0 < value <= 4_194_304
            for value in (postgres_pid, host_pid)
        ):
            raise ValueError("observer_signal_target_invalid")
        payload: dict[str, Any] = {
            "schema_version": "mindscape.postgres-signal-observer-target.v1",
            "target_postgres_pid": postgres_pid,
            "target_host_pid": host_pid,
        }
        if correlation is not None:
            from .pgbouncer import validate_pgbouncer_correlation

            payload = {
                **payload,
                "schema_version": "mindscape.postgres-signal-observer-target.v2",
                "pgbouncer": validate_pgbouncer_correlation(
                    dict(correlation),
                    target_postgres_pid=postgres_pid,
                ),
            }
        encoded = (
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("ascii")
        self._ensure_root()
        with self._lock():
            nofollow = getattr(os, "O_NOFOLLOW", None)
            if nofollow is None:
                raise RuntimeError("observer_signal_target_write_failed")
            descriptor: int | None = None
            identity: os.stat_result | None = None

            def unlink_owned() -> bool:
                if identity is None:
                    return True
                try:
                    current = os.lstat(self.signal_target_path)
                except FileNotFoundError:
                    return True
                except OSError:
                    return False
                if (current.st_dev, current.st_ino) != (
                    identity.st_dev,
                    identity.st_ino,
                ):
                    return False
                try:
                    self.signal_target_path.unlink()
                except OSError:
                    return False
                return True

            try:
                descriptor = os.open(
                    self.signal_target_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                    0o600,
                )
                identity = os.fstat(descriptor)
                if not stat.S_ISREG(identity.st_mode) or (
                    stat.S_IMODE(identity.st_mode) != 0o600
                ):
                    raise OSError("observer signal target identity invalid")
                offset = 0
                while offset < len(encoded):
                    written = os.write(descriptor, encoded[offset:])
                    if written <= 0:
                        raise OSError("observer signal target write stalled")
                    offset += written
                os.fsync(descriptor)
                final_status = os.fstat(descriptor)
                if (
                    (final_status.st_dev, final_status.st_ino)
                    != (identity.st_dev, identity.st_ino)
                    or final_status.st_size != len(encoded)
                ):
                    raise OSError("observer signal target readback invalid")
                os.close(descriptor)
                descriptor = None
            except OSError as exc:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                failure = (
                    "observer_signal_target_write_failed"
                    if unlink_owned()
                    else "observer_signal_target_cleanup_incomplete"
                )
                raise RuntimeError(failure) from exc

    def consume_signal_target_mapping(
        self, host_pid: int
    ) -> dict[str, Any] | None:
        """Consume the exact PID and optional pre-signal correlation mapping."""

        if type(host_pid) is not int or not 0 < host_pid <= 4_194_304:
            raise ValueError("observer_signal_target_host_pid_invalid")
        with self._lock():
            nofollow = getattr(os, "O_NOFOLLOW", None)
            if nofollow is None:
                raise RuntimeError("observer_signal_target_read_failed")
            try:
                status = os.lstat(self.signal_target_path)
            except FileNotFoundError:
                return None
            if not stat.S_ISREG(status.st_mode) or (
                stat.S_IMODE(status.st_mode) != 0o600
            ):
                raise RuntimeError("observer_signal_target_identity_invalid")
            descriptor: int | None = None
            try:
                descriptor = os.open(
                    self.signal_target_path,
                    os.O_RDONLY | nofollow,
                )
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or stat.S_IMODE(opened.st_mode) != 0o600
                    or (opened.st_dev, opened.st_ino)
                    != (status.st_dev, status.st_ino)
                ):
                    raise OSError("observer signal target identity changed")
                chunks: list[bytes] = []
                remaining = 2049
                while remaining > 0:
                    chunk = os.read(descriptor, remaining)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                encoded = b"".join(chunks)
            except (OSError, ValueError, TypeError) as exc:
                raise RuntimeError("observer_signal_target_read_failed") from exc
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError as exc:
                        raise RuntimeError(
                            "observer_signal_target_read_failed"
                        ) from exc
            try:
                payload = json.loads(encoded)
            except (ValueError, TypeError) as exc:
                raise RuntimeError("observer_signal_target_read_failed") from exc
            base_keys = {
                "schema_version",
                "target_postgres_pid",
                "target_host_pid",
            }
            if len(encoded) > 2048 or type(payload) is not dict:
                raise RuntimeError("observer_signal_target_payload_invalid")
            schema_version = payload.get("schema_version")
            expected_keys = (
                base_keys | {"pgbouncer"}
                if schema_version == "mindscape.postgres-signal-observer-target.v2"
                else base_keys
            )
            if (
                set(payload) != expected_keys
                or schema_version
                not in {
                    "mindscape.postgres-signal-observer-target.v1",
                    "mindscape.postgres-signal-observer-target.v2",
                }
                or type(payload.get("target_postgres_pid")) is not int
                or not 0 < payload["target_postgres_pid"] <= 4_194_304
                or type(payload.get("target_host_pid")) is not int
                or not 0 < payload["target_host_pid"] <= 4_194_304
            ):
                raise RuntimeError("observer_signal_target_payload_invalid")
            if schema_version.endswith(".v2"):
                from .pgbouncer import validate_pgbouncer_correlation

                try:
                    payload["pgbouncer"] = validate_pgbouncer_correlation(
                        payload.get("pgbouncer"),
                        target_postgres_pid=payload["target_postgres_pid"],
                    )
                except RuntimeError as exc:
                    raise RuntimeError(
                        "observer_signal_target_payload_invalid"
                    ) from exc
            if payload["target_host_pid"] != host_pid:
                return None
            try:
                current = os.lstat(self.signal_target_path)
                if (current.st_dev, current.st_ino) != (
                    status.st_dev,
                    status.st_ino,
                ):
                    raise OSError("observer signal target identity changed")
                self.signal_target_path.unlink()
            except OSError as exc:
                raise RuntimeError("observer_signal_target_consume_failed") from exc
            return dict(payload)

    def consume_signal_target(self, host_pid: int) -> int | None:
        """Consume one mapping and return its PostgreSQL namespace PID."""

        payload = self.consume_signal_target_mapping(host_pid)
        if payload is None:
            return None
        return int(payload["target_postgres_pid"])
