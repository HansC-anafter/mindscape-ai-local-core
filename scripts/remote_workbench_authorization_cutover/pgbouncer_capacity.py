"""Redacted PgBouncer capacity identity for Phase06 resource windows."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from .io import (
    CommandExecutor,
    CutoverError,
    assert_private_file,
    write_private_json,
)
from .pgbouncer_admin import pgbouncer_admin_csv_command


CAPACITY_KEYS = (
    "pool_mode",
    "default_pool_size",
    "min_pool_size",
    "reserve_pool_size",
    "max_client_conn",
    "max_db_connections",
    "max_user_connections",
)
_INTEGER_KEYS = frozenset(CAPACITY_KEYS) - {"pool_mode"}
_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SOURCE_MAX_BYTES = 65_536


class PgBouncerCapacityGate:
    """Capture and compare only non-secret pool capacity configuration."""

    def __init__(self, *, repo_root: Path, executor: CommandExecutor) -> None:
        self.repo_root = repo_root.resolve()
        self.executor = executor

    def _source_sha256(self) -> str:
        path = self.repo_root / "docker/pgbouncer/pgbouncer.ini"
        if path.is_symlink() or not path.is_file():
            raise CutoverError("Canonical PgBouncer source config is unavailable")
        payload = path.read_bytes()
        if not payload or len(payload) > _SOURCE_MAX_BYTES:
            raise CutoverError("Canonical PgBouncer source config exceeds its byte budget")
        return hashlib.sha256(payload).hexdigest()

    def capture(self) -> dict[str, Any]:
        """Read one bounded SHOW CONFIG projection without credentials."""

        raw = self.executor.run(
            pgbouncer_admin_csv_command("SHOW CONFIG;"),
            timeout_seconds=20.0,
        )
        rows = list(csv.DictReader(io.StringIO(raw)))
        values: dict[str, str] = {}
        for row in rows:
            key = str(row.get("key") or "").strip()
            if key not in CAPACITY_KEYS:
                continue
            if key in values:
                raise CutoverError("PgBouncer capacity config contains duplicate keys")
            values[key] = str(row.get("value") or "").strip()
        if set(values) != set(CAPACITY_KEYS) or values["pool_mode"] != "transaction":
            raise CutoverError("PgBouncer capacity config is incomplete or unsupported")
        for key in _INTEGER_KEYS:
            try:
                parsed = int(values[key])
            except ValueError as error:
                raise CutoverError("PgBouncer capacity value is not an integer") from error
            if parsed < 0 or str(parsed) != values[key]:
                raise CutoverError("PgBouncer capacity value is not canonical")
        return {
            "schema_version": 1,
            "source_config_sha256": self._source_sha256(),
            "capacity": {key: values[key] for key in CAPACITY_KEYS},
        }

    @staticmethod
    def _load_baseline(path: Path) -> dict[str, Any]:
        assert_private_file(path, max_bytes=4_096)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CutoverError("PgBouncer capacity baseline is malformed") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "source_config_sha256", "capacity"}
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("source_config_sha256"), str)
            or len(payload["source_config_sha256"]) != 64
            or not isinstance(payload.get("capacity"), dict)
            or set(payload["capacity"]) != set(CAPACITY_KEYS)
        ):
            raise CutoverError("PgBouncer capacity baseline identity is invalid")
        return payload

    def verify_and_persist(self, secure_dir: Path, label: str) -> dict[str, Any]:
        """Create the one baseline or require exact equality on every later gate."""

        if not _LABEL_PATTERN.fullmatch(label):
            raise CutoverError("PgBouncer capacity evidence label is invalid")
        current = self.capture()
        baseline_path = secure_dir / "pgbouncer-capacity-before.json"
        if baseline_path.exists() or baseline_path.is_symlink():
            baseline = self._load_baseline(baseline_path)
            if current != baseline:
                raise CutoverError("PgBouncer capacity or source config drifted")
        else:
            write_private_json(baseline_path, current)
        write_private_json(secure_dir / f"pgbouncer-capacity-{label}.json", current)
        return current
