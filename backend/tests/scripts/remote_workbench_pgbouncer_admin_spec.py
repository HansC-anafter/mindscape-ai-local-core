from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.pgbouncer_admin import (
    pgbouncer_admin_csv_command,
)


@pytest.mark.parametrize("query", ("SHOW POOLS;", "SHOW CONFIG;"))
def test_admin_command_keeps_secret_expansion_inside_the_container(query: str) -> None:
    command = pgbouncer_admin_csv_command(query)

    assert command[:7] == [
        "docker",
        "exec",
        "mindscape-ai-local-core-pgbouncer",
        "sh",
        "-c",
        'PGPASSWORD="$POSTGRES_CORE_PASSWORD" exec "$@"',
        "pgbouncer-admin",
    ]
    assert command[7:] == [
        "psql",
        "-X",
        "--no-password",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "mindscape",
        "-h",
        "127.0.0.1",
        "-p",
        "6432",
        "-d",
        "pgbouncer",
        "--csv",
        "-c",
        query,
    ]
    assert query not in command[5]
    assert not any("postgresql://" in argument for argument in command)


@pytest.mark.parametrize(
    "query",
    ("", "SHOW USERS;", "SHOW POOLS", "show pools;", "SHOW POOLS; SELECT 1;"),
)
def test_admin_command_rejects_every_non_allowlisted_query(query: str) -> None:
    with pytest.raises(CutoverError, match="not allowlisted"):
        pgbouncer_admin_csv_command(query)
