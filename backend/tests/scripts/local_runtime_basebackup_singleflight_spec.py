import importlib.util
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_incremental_backup():
    path = REPO_ROOT / "scripts" / "local_runtime_incremental_backup.py"
    spec = importlib.util.spec_from_file_location(
        "local_runtime_incremental_backup_singleflight_spec",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_basebackup_is_container_singleflight_and_interrupt_cleanup_is_marker_bound(
    monkeypatch,
    tmp_path,
):
    incremental = _load_incremental_backup()
    calls = []

    def fake_run_text(cmd, timeout=None):
        calls.append((cmd, timeout))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return ""

    monkeypatch.setattr(incremental, "run_text", fake_run_text)

    with pytest.raises(subprocess.TimeoutExpired):
        incremental.run_pg_basebackup(
            "base_20260715T000000Z",
            tmp_path / "postgres-wal-archive",
            600,
        )

    start_command = calls[0][0][-1]
    cleanup_command = calls[1][0][-1]
    assert "command -v flock" in start_command
    assert ".pg_basebackup.lock" in start_command
    assert "flock -n 9" in start_command
    assert "postgres_basebackup_already_running" in start_command
    assert start_command.index("flock -n 9") < start_command.index("rm -rf")
    assert ".pg_basebackup-client.pid" in start_command
    assert "backup_client_pid=$!" in start_command
    assert "/proc/$backup_client_pid/cmdline" in cleanup_command
    assert "pg_basebackup\\ *|*/pg_basebackup\\ *" in cleanup_command
    assert 'kill -TERM "$backup_client_pid"' in cleanup_command
    assert "pg_stat_activity" not in cleanup_command
