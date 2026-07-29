from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.routes.core.capability_install_core.install_commit_coordinator import (
    InstallCommitCoordinator,
    InstallCommitState,
)
from backend.app.services.install_result import InstallResult
from backend.app.services.runtime_assets_installer import RuntimeAssetsInstaller
from backend.app.services.capability_install_jobs_core import terminal_commit
from backend.app.services.pack_install_truth_committer import PackInstallTruthCommitter


def _candidate(tmp_path: Path) -> Path:
    cap_dir = tmp_path / "candidate" / "demo"
    (cap_dir / "services").mkdir(parents=True)
    (cap_dir / "manifest.yaml").write_text(
        "code: demo\nversion: 2.0.0\n",
        encoding="utf-8",
    )
    (cap_dir / "services" / "runtime.py").write_text(
        "VERSION = 2\n",
        encoding="utf-8",
    )
    return cap_dir


def _write_migration_contract(cap_dir: Path, *, body: str) -> None:
    (cap_dir / "migrations" / "versions").mkdir(parents=True, exist_ok=True)
    (cap_dir / "migrations.yaml").write_text(
        "migration_paths:\n  - migrations/versions/\nrevisions:\n  - demo_001\n",
        encoding="utf-8",
    )
    (cap_dir / "migrations" / "versions" / "demo_001.py").write_text(
        body,
        encoding="utf-8",
    )


def _coordinator(tmp_path: Path):
    root = tmp_path / "local-core"
    capabilities_dir = root / "backend" / "app" / "capabilities"
    live = capabilities_dir / "demo"
    (live / "services").mkdir(parents=True)
    (live / "manifest.yaml").write_text(
        "code: demo\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    (live / "services" / "runtime.py").write_text(
        "VERSION = 1\n",
        encoding="utf-8",
    )
    installer = RuntimeAssetsInstaller(root, capabilities_dir)
    coordinator = InstallCommitCoordinator(
        install_id="install-1",
        capability_code="demo",
        runtime_installer=installer,
    )
    return coordinator, live


def test_identical_migration_contract_skips_database_execution(tmp_path: Path) -> None:
    coordinator, live = _coordinator(tmp_path)
    candidate = _candidate(tmp_path)
    migration_body = (
        'revision = "demo_001"\n'
        "down_revision = None\n"
        "def upgrade():\n"
        "    pass\n"
    )
    _write_migration_contract(live, body=migration_body)
    _write_migration_contract(candidate, body=migration_body)
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=candidate,
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    migration_calls: list[str] = []
    coordinator.runtime_installer.execute_migrations = (
        lambda *_args: migration_calls.append("called")
    )

    coordinator.execute_candidate_migrations(result)

    assert migration_calls == []
    assert result.migration_status == {"demo": "skipped"}
    receipt = result.migration_receipts["demo"]
    assert receipt["mode"] == "identical_installed_migration_contract"
    assert receipt["schema_mutation_required"] is False
    assert receipt["database_operations"] == 0
    assert receipt["candidate_digest"] == receipt["installed_digest"]


def test_runtime_bytecode_does_not_break_migration_contract_equivalence(
    tmp_path: Path,
) -> None:
    coordinator, live = _coordinator(tmp_path)
    candidate = _candidate(tmp_path)
    migration_body = (
        'revision = "demo_001"\n'
        "down_revision = None\n"
        "def upgrade():\n"
        "    pass\n"
    )
    _write_migration_contract(live, body=migration_body)
    _write_migration_contract(candidate, body=migration_body)
    cache = live / "migrations" / "versions" / "__pycache__"
    cache.mkdir()
    (cache / "demo_001.cpython-311.pyc").write_bytes(b"runtime-only")
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=candidate,
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    migration_calls: list[str] = []
    coordinator.runtime_installer.execute_migrations = (
        lambda *_args: migration_calls.append("called")
    )

    coordinator.execute_candidate_migrations(result)

    assert migration_calls == []
    assert result.migration_status == {"demo": "skipped"}


def test_changed_migration_contract_uses_existing_execution_path(tmp_path: Path) -> None:
    coordinator, live = _coordinator(tmp_path)
    candidate = _candidate(tmp_path)
    _write_migration_contract(
        live,
        body='revision = "demo_001"\ndown_revision = None\ndef upgrade():\n    pass\n',
    )
    _write_migration_contract(
        candidate,
        body=(
            'revision = "demo_001"\n'
            "down_revision = None\n"
            "def upgrade():\n"
            "    create_new_schema()\n"
        ),
    )
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=candidate,
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    migration_calls: list[str] = []

    def execute_migrations(capability_code: str, install_result: InstallResult) -> None:
        migration_calls.append(capability_code)
        install_result.migration_status = {capability_code: "applied"}

    coordinator.runtime_installer.execute_migrations = execute_migrations

    coordinator.execute_candidate_migrations(result)

    assert migration_calls == ["demo"]
    assert result.migration_status == {"demo": "applied"}


def test_candidate_prepare_does_not_mutate_live_and_restore_is_exact(tmp_path: Path) -> None:
    coordinator, live = _coordinator(tmp_path)
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=_candidate(tmp_path),
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    assert "version: 1.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")

    coordinator.runtime_installer.execute_migrations = lambda *_args: None
    coordinator.execute_candidate_migrations(result)
    coordinator.publish()
    assert "version: 2.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")

    coordinator.restore_previous()
    assert coordinator.state is InstallCommitState.RESTORED_PREVIOUS
    assert "version: 1.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")
    assert coordinator.prepared is not None
    assert coordinator.prepared.staging_cap_dir.exists()


def test_previous_is_deleted_only_after_commit_and_finalize(tmp_path: Path) -> None:
    coordinator, live = _coordinator(tmp_path)
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=_candidate(tmp_path),
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    coordinator.runtime_installer.execute_migrations = lambda *_args: None
    coordinator.execute_candidate_migrations(result)
    coordinator.publish()
    assert coordinator.prepared is not None
    assert coordinator.prepared.previous_cap_dir.exists()

    coordinator.mark_activated()
    coordinator.mark_committed()
    coordinator.finalize()

    assert coordinator.state is InstallCommitState.SUCCEEDED
    assert not coordinator.prepared.previous_root.exists()
    assert "version: 2.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")


def test_publish_is_forbidden_before_migration_success(tmp_path: Path) -> None:
    coordinator, _ = _coordinator(tmp_path)
    coordinator.prepare(
        cap_dir=_candidate(tmp_path),
        manifest={"code": "demo", "version": "2.0.0"},
        result=InstallResult(capability_code="demo"),
        temp_dir=None,
    )

    with pytest.raises(RuntimeError, match="migration_applied"):
        coordinator.publish()


def test_previous_restore_is_forbidden_after_truth_commit(tmp_path: Path) -> None:
    coordinator, live = _coordinator(tmp_path)
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=_candidate(tmp_path),
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    coordinator.runtime_installer.execute_migrations = lambda *_args: None
    coordinator.execute_candidate_migrations(result)
    coordinator.publish()
    coordinator.mark_activated()
    coordinator.mark_committed()

    with pytest.raises(RuntimeError, match="forbidden_after_truth_commit"):
        coordinator.restore_previous()

    assert "version: 2.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")


def test_finalize_failure_becomes_cleanup_pending_without_runtime_restore(
    monkeypatch,
    tmp_path: Path,
) -> None:
    coordinator, live = _coordinator(tmp_path)
    result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=_candidate(tmp_path),
        manifest={"code": "demo", "version": "2.0.0"},
        result=result,
        temp_dir=None,
    )
    coordinator.runtime_installer.execute_migrations = lambda *_args: None
    coordinator.execute_candidate_migrations(result)
    coordinator.publish()
    coordinator.mark_activated()
    coordinator.mark_committed()
    monkeypatch.setattr(
        coordinator.runtime_installer,
        "finalize_publish",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    with pytest.raises(RuntimeError, match="cleanup failed"):
        coordinator.finalize()
    coordinator.mark_cleanup_pending(RuntimeError("cleanup failed"))

    assert coordinator.state is InstallCommitState.COMMITTED_CLEANUP_PENDING
    assert "version: 2.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")


def test_terminal_cleanup_failure_keeps_committed_candidate(monkeypatch, tmp_path: Path):
    coordinator, live = _coordinator(tmp_path)
    install_result = InstallResult(capability_code="demo")
    coordinator.prepare(
        cap_dir=_candidate(tmp_path),
        manifest={"code": "demo", "version": "2.0.0"},
        result=install_result,
        temp_dir=None,
    )
    coordinator.runtime_installer.execute_migrations = lambda *_args: None
    coordinator.execute_candidate_migrations(install_result)
    coordinator.publish()
    monkeypatch.setattr(
        coordinator.runtime_installer,
        "finalize_publish",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    committed_inputs = {}

    class _Committer:
        def __init__(self, **_kwargs):
            pass

        def commit(self, **kwargs):
            committed_inputs.update(kwargs)
            return {"install_id": kwargs["install_id"]}

    class _Store:
        db_role = "core"

        def get_job(self, install_id):
            return {"install_id": install_id, "state": "succeeded"}

    monkeypatch.setattr(terminal_commit, "PackInstallTruthCommitter", _Committer)
    monkeypatch.setattr(
        terminal_commit,
        "clear_installed_capability_metadata_caches",
        lambda **_kwargs: None,
    )
    reconciliation = []
    monkeypatch.setattr(
        terminal_commit,
        "record_projection_result",
        lambda install_id, **kwargs: reconciliation.append(
            ("projection", install_id, kwargs)
        ),
    )
    monkeypatch.setattr(
        terminal_commit,
        "record_filesystem_cleanup_result",
        lambda install_id, **kwargs: reconciliation.append(
            ("cleanup", install_id, kwargs)
        ),
    )
    monkeypatch.setattr(
        terminal_commit,
        "PackInstallReconciliationStore",
        lambda **_kwargs: SimpleNamespace(get=lambda _install_id: None),
    )
    result = SimpleNamespace(
        install_commit_coordinator=coordinator,
        activation_candidate={"manifest_hash": "a" * 64, "migration_state": "applied"},
    )
    committed = terminal_commit.commit_succeeded_install(
        service=SimpleNamespace(store=_Store()),
        job={"install_id": "install-1", "source_payload": {}},
        result=result,
        payload={
            "capability_code": "demo",
            "version": "2.0.0",
            "migration_receipts": {},
            "pack_metadata": {"install_projection_manifest": {}},
            "restart_decision": {
                "execution_activation_state": "activated",
                "runner_restart_required": False,
            },
            "restart_required": False,
            "backend_process_restart_required": False,
            "runner_restart_required": False,
            "execution_activation_required": True,
            "execution_activation_state": "activated",
            "restart_semantics_version": "install_restart_decision_v2",
        },
        execution_activation={"state": "activated"},
    )

    assert committed["state"] == "succeeded"
    assert coordinator.state is InstallCommitState.COMMITTED_CLEANUP_PENDING
    assert "version: 2.0.0" in (live / "manifest.yaml").read_text(encoding="utf-8")
    assert committed_inputs["commit_metadata"]["restart_decision"][
        "execution_activation_state"
    ] == "activated"
    assert (
        committed_inputs["commit_metadata"]["execution_activation_state"]
        == "activated"
    )
    assert committed_inputs["commit_metadata"]["runner_restart_required"] is False
    assert reconciliation[0] == (
        "projection",
        "install-1",
        {"succeeded": True, "error": None},
    )
    assert reconciliation[1][0:2] == ("cleanup", "install-1")
    assert reconciliation[1][2]["succeeded"] is False


def test_truth_commit_retry_returns_original_receipt_without_rewriting_truth():
    committed_at = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    existing = SimpleNamespace(
        pack_id="demo",
        version="2.0.0",
        manifest_hash="a" * 64,
        artifact_sha256="b" * 64,
        committed_at=committed_at,
    )

    class _Result:
        def __init__(self, *, row=None, scalar_value=None):
            self.row = row
            self.scalar_value = scalar_value

        def fetchone(self):
            return self.row

        def scalar(self):
            return self.scalar_value

    class _Connection:
        def __init__(self):
            self.statements = []

        def execute(self, statement, _params):
            source = str(statement)
            self.statements.append(source)
            if "FROM pack_install_commit_receipts" in source:
                return _Result(row=existing)
            if "FROM capability_install_jobs" in source:
                return _Result(scalar_value="succeeded")
            raise AssertionError("idempotent retry must not issue a write")

    connection = _Connection()

    @contextmanager
    def _transaction():
        yield connection

    committer = object.__new__(PackInstallTruthCommitter)
    committer.transaction = _transaction

    receipt = committer.commit(
        install_id="install-1",
        pack_id="demo",
        version="2.0.0",
        manifest_hash="a" * 64,
        artifact_sha256="b" * 64,
        migration_receipt={},
        commit_metadata={},
        activation={},
        result_payload={},
    )

    assert receipt["committed_at"] == committed_at.isoformat()
    assert len(connection.statements) == 2
