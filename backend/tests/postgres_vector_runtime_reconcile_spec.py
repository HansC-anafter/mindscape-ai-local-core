from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RECONCILE_SCRIPT = REPO_ROOT / "docker/postgres/reconcile-vector-runtime-role.sh"


def _write_fake_psql(bin_dir: Path) -> Path:
    fake = bin_dir / "psql"
    fake.write_text(
        """#!/bin/sh
set -eu
args="$*"
if printf '%s' "$args" | grep -q -- '-Atc'; then
  printf 'probe\\n' >> "$FAKE_PSQL_LOG"
  if [ -f "$FAKE_PSQL_STATE" ] && [ "${PGPASSWORD:-}" = "$FAKE_EXPECTED_SECRET" ]; then
    printf '1\\n'
    exit 0
  fi
  exit 1
fi
if printf '%s' "$args" | grep -q -- '-At'; then
  printf 'role-state\\n' >> "$FAKE_PSQL_LOG"
  printf '1|t|f|f|f|f|f\\n'
  exit 0
fi
printf 'mutation\\n' >> "$FAKE_PSQL_LOG"
touch "$FAKE_PSQL_STATE"
exit 0
""",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def _run_reconcile(
    tmp_path: Path,
    *,
    converged: bool,
    secret_content: str = "synthetic-new-secret",
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_psql(bin_dir)
    state_file = tmp_path / "state"
    if converged:
        state_file.touch()
    log_file = tmp_path / "psql.log"
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_text(secret_content, encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE": str(secret_file),
        "POSTGRES_VECTOR_RUNTIME_USER": "mindscape_vector_runtime",
        "POSTGRES_VECTOR_DB": "mindscape_vectors",
        "POSTGRES_CORE_USER": "mindscape",
        "POSTGRES_CORE_PASSWORD": "synthetic-admin-secret",
        "POSTGRES_DIRECT_HOST": "postgres",
        "FAKE_PSQL_STATE": str(state_file),
        "FAKE_PSQL_LOG": str(log_file),
        "FAKE_EXPECTED_SECRET": "synthetic-new-secret",
    }
    return subprocess.run(
        ["sh", str(RECONCILE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_reconcile_skips_mutation_when_role_and_password_are_valid(tmp_path):
    result = _run_reconcile(tmp_path, converged=True)
    actions = (tmp_path / "psql.log").read_text(encoding="utf-8").splitlines()

    assert actions == ["role-state", "probe"]
    assert "already converged" in result.stdout
    assert "synthetic-new-secret" not in result.stdout + result.stderr


def test_reconcile_mutates_once_then_verifies_new_password(tmp_path):
    result = _run_reconcile(tmp_path, converged=False)
    actions = (tmp_path / "psql.log").read_text(encoding="utf-8").splitlines()

    assert actions == ["role-state", "probe", "mutation", "probe"]
    assert "role reconciled" in result.stdout
    assert "synthetic-new-secret" not in result.stdout + result.stderr


def test_reconcile_fails_before_psql_when_secret_is_missing(tmp_path):
    result = subprocess.run(
        ["sh", str(RECONCILE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE": str(tmp_path / "missing"),
        },
    )

    assert result.returncode != 0
    assert "secret file is unavailable" in result.stderr


def test_reconcile_rejects_multiline_secret_before_psql(tmp_path):
    with pytest.raises(subprocess.CalledProcessError) as error:
        _run_reconcile(
            tmp_path,
            converged=False,
            secret_content="first-line\nsecond-line",
        )

    result = error.value
    assert "exactly one line" in result.stderr
    assert not (tmp_path / "psql.log").exists()
    assert "first-line" not in result.stdout + result.stderr
