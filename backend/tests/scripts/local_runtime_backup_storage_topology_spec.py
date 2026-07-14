import importlib.util
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


incremental = _load_module(
    "local_runtime_incremental_backup_storage_topology",
    REPO_ROOT / "scripts" / "local_runtime_incremental_backup.py",
)
backup_job = _load_module(
    "local_runtime_backup_job_storage_topology",
    REPO_ROOT / "scripts" / "local_runtime_backup_job.py",
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
        "mirror_scopes": None,
        "postgres_only": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_default_backup_roots_are_siblings_of_runtime_data(monkeypatch, tmp_path):
    data_root = tmp_path / "runtime" / "data"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", "")
    monkeypatch.setattr(incremental, "resolve_data_host_dir", lambda: data_root)
    monkeypatch.setattr(backup_job._common, "resolve_data_host_dir", lambda: data_root)

    expected = data_root.parent / "backups" / "local-runtime"

    assert incremental.build_config(_args())["primary_root"] == expected
    assert backup_job.resolve_backup_root(None) == expected


def test_plan_rejects_backup_root_inside_runtime_bind_before_admission(monkeypatch, tmp_path):
    data_root = tmp_path / "runtime" / "data"
    nested_backup = data_root / "backups" / "local-runtime"
    admission_called = False

    def inspect_admission(**_kwargs):
        nonlocal admission_called
        admission_called = True
        raise AssertionError("runtime admission must not run for invalid storage topology")

    monkeypatch.setenv("LOCAL_CORE_DATA_HOST_DIR", str(data_root))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(nested_backup))
    monkeypatch.setenv(
        "LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR",
        str(nested_backup / "postgres-wal-archive"),
    )
    monkeypatch.setattr(incremental, "inspect_backup_runtime_admission", inspect_admission)

    plan = incremental.build_plan(_args())

    assert admission_called is False
    assert plan["preflight_status"] == "topology_blocked"
    assert plan["blocking_reasons"] == ["backup_root_inside_runtime_bind_mount"]
    assert plan["storage_topology"] == {
        "runtime_data_root": str(data_root),
        "backup_root": str(nested_backup),
        "isolated_from_runtime_bind": False,
    }
