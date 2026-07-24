import importlib.util
import json
import os
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.local_runtime_incremental_backup_lib import runtime_admission


_ACTIVE_RUNNER_HEARTBEAT_COUNTS = runtime_admission.active_runner_heartbeat_counts


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


incremental = _load_module(
    "local_runtime_incremental_backup_admission_spec",
    REPO_ROOT / "scripts" / "local_runtime_incremental_backup.py",
)


def _args(**overrides):
    values = {
        "output_dir": None,
        "mirror_root": None,
        "retention_local_count": None,
        "retention_mirror_count": None,
        "min_free_gb": None,
        "require_mirror": None,
        "base_interval_hours": None,
    }
    values.update(overrides)
    return Namespace(**values)


def _postgres_ok():
    return {
        "archive_mode": "on",
        "archive_command": "/usr/local/bin/mindscape-archive-wal %p %f /archive",
        "wal_ready_count": 0,
        "wal_bytes": 1024,
        "archiver_archived_count": 1,
        "archiver_last_archived_wal": "000000010000000000000001",
        "archiver_last_archived_time": "2026-05-25T00:00:00+00:00",
        "archiver_failed_count": 0,
        "archiver_last_failed_wal": "",
        "archiver_last_failed_time": "",
        "archiver_stats_reset": "2026-05-25T00:00:00+00:00",
    }


def _runtime_admitted():
    return {
        "schema_version": "backup_runtime_admission.v4",
        "backup_scope": "runtime_snapshot_and_postgres_chain",
        "admitted": True,
        "active_meeting_sessions": 0,
        "active_postgres_base_backups": 0,
        "active_runner_tasks": 0,
        "active_runner_heartbeats": 0,
        "active_runner_inflight": 0,
        "active_runner_capacity": 0,
        "active_live_media_receivers": [],
        "receiver_state_root": "/runtime/live-media-receivers",
        "blocking_reasons": [],
        "inspection_errors": [],
    }


def _write_state(path: Path, *, state: str, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "live_media_receiver_state.v1",
                "workspace_id": "workspace-test",
                "media_session_id": path.name.removesuffix(".state.json"),
                "receiver_identity": "receiver-test",
                "pid": pid,
                "state": state,
                "updated_at": "2026-07-14T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _idle_runner_heartbeats(monkeypatch):
    monkeypatch.setattr(
        runtime_admission,
        "active_runner_heartbeat_counts",
        lambda: {"count": 4, "inflight": 0, "capacity": 7, "malformed": 0},
    )


def test_incremental_backup_facade_uses_repo_root():
    assert incremental.REPO_ROOT == REPO_ROOT
    assert incremental.VERIFY_SCRIPT == REPO_ROOT / "scripts" / "verify_local_runtime_backup.sh"


def test_basebackup_interrupt_cleanup_is_marker_bound_and_client_validated(
    monkeypatch, tmp_path
):
    calls = []

    def fake_run_text(cmd, timeout=None):
        calls.append((cmd, timeout))
        if len(calls) == 1:
            raise KeyboardInterrupt()
        return ""

    monkeypatch.setattr(incremental, "run_text", fake_run_text)

    with pytest.raises(KeyboardInterrupt):
        incremental.run_pg_basebackup(
            "base_20260715T000000Z",
            tmp_path / "postgres-wal-archive",
            600,
        )

    start_command = calls[0][0][-1]
    cleanup_command = calls[1][0][-1]
    assert "pg_basebackup" in start_command
    assert "command -v flock" not in start_command
    assert ".pg_basebackup.lock.d" in start_command
    assert "postgres_basebackup_already_running" in start_command
    assert "trap cleanup_backup_lock EXIT INT TERM HUP" in start_command
    assert start_command.index(
        "mkdir /var/lib/postgresql/wal_archive/.pg_basebackup.lock.d"
    ) < start_command.index("rm -rf")
    assert ".pg_basebackup.lock.d/client.pid" in start_command
    assert "backup_client_pid=$!" in start_command
    assert "backup_client_status" in start_command
    assert "test -r" in cleanup_command
    assert "marker_wait" in cleanup_command
    assert "/proc/$backup_client_pid/cmdline" in cleanup_command
    assert "pg_basebackup\\ *|*/pg_basebackup\\ *" in cleanup_command
    assert 'kill -TERM "$backup_client_pid"' in cleanup_command
    assert "pg_stat_activity" not in cleanup_command


def test_policy_defers_backup_for_active_live_practice(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    wal_root = primary / "postgres-wal-archive"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_REQUIRE_MIRROR", "false")
    monkeypatch.delenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: True)
    monkeypatch.setattr(incremental, "postgres_status", _postgres_ok)
    monkeypatch.setattr(
        incremental,
        "inspect_backup_runtime_admission",
        lambda **_kwargs: {
            **_runtime_admitted(),
            "admitted": False,
            "active_meeting_sessions": 1,
            "blocking_reasons": ["active_meeting_sessions"],
        },
    )

    plan = incremental.build_plan(_args())

    assert plan["can_run"] is False
    assert plan["runtime_admission"]["active_meeting_sessions"] == 1
    assert "active_meeting_sessions" in plan["blocking_reasons"]


def test_postgres_only_plan_requires_explicit_local_only_scope(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    wal_root = primary / "postgres-wal-archive"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", str(mirror))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: False)
    monkeypatch.setattr(incremental, "postgres_status", _postgres_ok)

    blocked = incremental.build_plan(_args(postgres_only=True))
    local_only = incremental.build_plan(
        _args(postgres_only=True, mirror_root="", require_mirror=False)
    )

    assert "postgres_only_requires_local_only" in blocked["blocking_reasons"]
    assert local_only["can_run"] is True
    assert local_only["policy"]["backup_scope"] == "postgres_chain_only"


def test_database_workload_probe_parses_meeting_and_basebackup_counts(monkeypatch):
    monkeypatch.setattr(
        runtime_admission,
        "run_text",
        lambda _cmd, timeout: "SET\n2|1|3\n",
    )

    assert runtime_admission.active_database_workload_counts() == {
        "active_meeting_sessions": 2,
        "active_postgres_base_backups": 1,
        "active_runner_tasks": 3,
    }


def test_postgres_chain_only_admission_does_not_wait_for_global_runner_idle(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        runtime_admission,
        "active_postgres_base_backup_count",
        lambda: 0,
    )
    monkeypatch.setattr(
        runtime_admission,
        "active_database_workload_counts",
        lambda: (_ for _ in ()).throw(AssertionError("global DB workloads must not be read")),
    )
    monkeypatch.setattr(
        runtime_admission,
        "active_runner_heartbeat_counts",
        lambda: (_ for _ in ()).throw(AssertionError("runner heartbeats must not be read")),
    )
    monkeypatch.setattr(
        runtime_admission,
        "inspect_live_media_receivers",
        lambda _path: (_ for _ in ()).throw(AssertionError("media state must not be read")),
    )

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=tmp_path / "postgres-wal-archive",
        backup_scope="postgres_chain_only",
    )

    assert result["admitted"] is True
    assert result["backup_scope"] == "postgres_chain_only"
    assert result["active_runner_tasks"] is None
    assert result["active_runner_inflight"] is None
    assert result["blocking_reasons"] == []


def test_postgres_chain_only_admission_blocks_concurrent_base_backup(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        runtime_admission,
        "active_postgres_base_backup_count",
        lambda: 1,
    )

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=tmp_path / "postgres-wal-archive",
        backup_scope="postgres_chain_only",
    )

    assert result["admitted"] is False
    assert result["blocking_reasons"] == ["postgres_basebackup_already_running"]


def test_admission_blocks_fresh_running_runner_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runtime_admission,
        "active_database_workload_counts",
        lambda: {
            "active_meeting_sessions": 0,
            "active_postgres_base_backups": 0,
            "active_runner_tasks": 2,
        },
    )

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=tmp_path / "postgres-wal-archive",
    )

    assert result["admitted"] is False
    assert result["active_runner_tasks"] == 2
    assert "active_runner_tasks" in result["blocking_reasons"]


def test_runner_heartbeat_probe_parses_aggregate_without_keys(monkeypatch):
    monkeypatch.setattr(
        runtime_admission,
        "active_runner_heartbeat_counts",
        _ACTIVE_RUNNER_HEARTBEAT_COUNTS,
    )
    monkeypatch.setattr(
        runtime_admission,
        "run_text",
        lambda _cmd, timeout: '{"count":4,"inflight":3,"capacity":7,"malformed":0}\n',
    )

    assert runtime_admission.active_runner_heartbeat_counts() == {
        "count": 4,
        "inflight": 3,
        "capacity": 7,
        "malformed": 0,
    }


def test_admission_blocks_runner_heartbeat_inflight(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runtime_admission,
        "active_database_workload_counts",
        lambda: {
            "active_meeting_sessions": 0,
            "active_postgres_base_backups": 0,
            "active_runner_tasks": 0,
        },
    )
    monkeypatch.setattr(
        runtime_admission,
        "active_runner_heartbeat_counts",
        lambda: {"count": 4, "inflight": 2, "capacity": 7, "malformed": 0},
    )

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=tmp_path / "postgres-wal-archive",
    )

    assert result["admitted"] is False
    assert result["active_runner_inflight"] == 2
    assert "active_runner_inflight" in result["blocking_reasons"]


def test_admission_fails_closed_for_malformed_runner_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runtime_admission,
        "active_database_workload_counts",
        lambda: {
            "active_meeting_sessions": 0,
            "active_postgres_base_backups": 0,
            "active_runner_tasks": 0,
        },
    )

    def malformed():
        raise RuntimeError("runner_heartbeat_counts_malformed")

    monkeypatch.setattr(runtime_admission, "active_runner_heartbeat_counts", malformed)

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=tmp_path / "postgres-wal-archive",
    )

    assert result["admitted"] is False
    assert result["active_runner_inflight"] is None
    assert "backup_runtime_admission_inspection_failed" in result["blocking_reasons"]


def test_receiver_admission_blocks_only_live_runtime_states(tmp_path):
    state_root = tmp_path / "runtime" / "live-media-receivers"
    _write_state(state_root / "live.state.json", state="analyzing", pid=os.getpid())
    _write_state(state_root / "complete.state.json", state="completed", pid=os.getpid())

    result = runtime_admission.inspect_live_media_receivers(tmp_path)

    assert [item["media_session_id"] for item in result["active"]] == ["live"]
    assert result["errors"] == []


def test_recent_pidless_start_is_admitted_as_active(tmp_path):
    state_path = (
        tmp_path / "runtime" / "live-media-receivers" / "pending.state.json"
    )
    _write_state(state_path, state="starting", pid=0)

    result = runtime_admission.inspect_live_media_receivers(
        tmp_path,
        now=datetime.now(timezone.utc),
    )

    assert result["active"][0]["media_session_id"] == "pending"
    assert result["active"][0]["pid_alive"] is False


def test_admission_fails_closed_when_meeting_inspection_fails(monkeypatch, tmp_path):
    def fail_meeting_query():
        raise RuntimeError("database_unavailable")

    monkeypatch.setattr(runtime_admission, "active_database_workload_counts", fail_meeting_query)

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=tmp_path / "postgres-wal-archive",
    )

    assert result["admitted"] is False
    assert result["active_meeting_sessions"] is None
    assert result["active_runner_tasks"] is None
    assert "backup_runtime_admission_inspection_failed" in result["blocking_reasons"]


def test_basebackup_lock_short_circuits_database_probe(monkeypatch, tmp_path):
    wal_root = tmp_path / "postgres-wal-archive"
    (wal_root / ".pg_basebackup.lock.d").mkdir(parents=True)

    def fail_if_queried():
        raise AssertionError("database probe must not run while the host lock is present")

    monkeypatch.setattr(
        runtime_admission,
        "active_database_workload_counts",
        fail_if_queried,
    )

    result = runtime_admission.inspect_backup_runtime_admission(
        data_host_dir=tmp_path,
        wal_archive_root=wal_root,
    )

    assert result["admitted"] is False
    assert result["active_postgres_base_backups"] == 1
    assert result["active_runner_tasks"] is None
    assert result["database_inspection_skipped"] is True
    assert "postgres_basebackup_already_running" in result["blocking_reasons"]
