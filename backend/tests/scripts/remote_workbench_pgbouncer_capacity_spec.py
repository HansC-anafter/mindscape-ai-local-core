from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.pgbouncer_capacity import (
    CAPACITY_KEYS,
    PgBouncerCapacityGate,
)


BASELINE = {
    "pool_mode": "transaction",
    "default_pool_size": "30",
    "min_pool_size": "5",
    "reserve_pool_size": "10",
    "max_client_conn": "500",
    "max_db_connections": "0",
    "max_user_connections": "0",
}


def _csv(values: dict[str, str]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=("key", "value", "default", "changeable"))
    writer.writeheader()
    for key in CAPACITY_KEYS:
        if key not in values:
            continue
        writer.writerow(
            {"key": key, "value": values[key], "default": "", "changeable": "yes"}
        )
    writer.writerow(
        {"key": "auth_file", "value": "/secret", "default": "", "changeable": "no"}
    )
    return output.getvalue()


class Executor:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls = []

    def run(self, args, **_kwargs) -> str:
        self.calls.append(list(args))
        return _csv(self.values)


def _gate(tmp_path: Path, executor: Executor) -> PgBouncerCapacityGate:
    source = tmp_path / "docker/pgbouncer/pgbouncer.ini"
    source.parent.mkdir(parents=True)
    source.write_text("[pgbouncer]\ndefault_pool_size = 30\n", encoding="utf-8")
    return PgBouncerCapacityGate(repo_root=tmp_path, executor=executor)


def test_capacity_gate_persists_only_redacted_subset_and_matches(tmp_path: Path) -> None:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    executor = Executor(dict(BASELINE))
    gate = _gate(tmp_path, executor)

    first = gate.verify_and_persist(secure, "preflight")
    second = gate.verify_and_persist(secure, "post-origin")

    assert first == second
    assert set(first["capacity"]) == set(CAPACITY_KEYS)
    assert "auth_file" not in str(first)
    assert (secure / "pgbouncer-capacity-before.json").stat().st_mode & 0o777 == 0o600
    assert len(executor.calls) == 2


def test_capacity_gate_rejects_larger_pool_even_without_waiter_signal(
    tmp_path: Path,
) -> None:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    executor = Executor(dict(BASELINE))
    gate = _gate(tmp_path, executor)
    gate.verify_and_persist(secure, "preflight")
    executor.values = {**BASELINE, "default_pool_size": "60"}

    with pytest.raises(CutoverError, match="drifted"):
        gate.verify_and_persist(secure, "post-origin")


@pytest.mark.parametrize(
    "values",
    (
        {key: value for key, value in BASELINE.items() if key != "max_user_connections"},
        {**BASELINE, "pool_mode": "session"},
        {**BASELINE, "max_client_conn": "0500"},
    ),
)
def test_capacity_gate_rejects_incomplete_or_noncanonical_config(
    tmp_path: Path,
    values: dict[str, str],
) -> None:
    gate = _gate(tmp_path, Executor(values))
    with pytest.raises(CutoverError):
        gate.capture()
