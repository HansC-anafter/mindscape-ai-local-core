from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.services import pack_install_reconciliation
from backend.app.services.pack_install_reconciliation_core.filesystem import (
    finalize_committed_filesystem,
)
from backend.app.services.pack_install_reconciliation_core.reconciler import (
    CommittedInstallReconciler,
)


def _filesystem_fixture(tmp_path: Path):
    root = tmp_path / "local-core"
    capabilities = root / "backend" / "app" / "capabilities"
    target = capabilities / "demo"
    target.mkdir(parents=True)
    manifest = target / "manifest.yaml"
    manifest.write_text("code: demo\nversion: 2.0.0\n", encoding="utf-8")
    previous = (
        capabilities.parent
        / ".capability-install-previous"
        / "install-1"
        / "demo"
    )
    previous.mkdir(parents=True)
    (previous / "old.txt").write_text("old", encoding="utf-8")
    staging = capabilities.parent / ".capability-install-staging" / "install-1"
    staging.mkdir(parents=True)
    (staging / "stale.txt").write_text("stale", encoding="utf-8")
    receipt = {
        "target_cap_dir": str(target),
        "previous_cap_dir": str(previous),
        "staging_root": str(staging),
    }
    return root, target, previous, staging, receipt, hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()


def test_committed_filesystem_cleanup_is_path_validated_and_idempotent(tmp_path: Path):
    root, target, previous, staging, receipt, manifest_hash = _filesystem_fixture(
        tmp_path
    )

    finalize_committed_filesystem(
        local_core_root=root,
        install_id="install-1",
        capability_code="demo",
        manifest_hash=manifest_hash,
        filesystem_receipt=receipt,
    )
    finalize_committed_filesystem(
        local_core_root=root,
        install_id="install-1",
        capability_code="demo",
        manifest_hash=manifest_hash,
        filesystem_receipt=receipt,
    )

    assert target.exists()
    assert not previous.parent.exists()
    assert not staging.exists()


def test_committed_filesystem_cleanup_rejects_target_path_substitution(tmp_path: Path):
    root, _target, _previous, _staging, receipt, manifest_hash = _filesystem_fixture(
        tmp_path
    )
    receipt["target_cap_dir"] = str(tmp_path)

    with pytest.raises(RuntimeError, match="target_path_mismatch"):
        finalize_committed_filesystem(
            local_core_root=root,
            install_id="install-1",
            capability_code="demo",
            manifest_hash=manifest_hash,
            filesystem_receipt=receipt,
        )


class _Store:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def next_due(self):
        return dict(self.row)

    def has_incomplete(self):
        return True

    def mark_projection(self, install_id, *, succeeded, error=None):
        self.calls.append(("projection", install_id, succeeded, error))
        self.row["projection_state"] = "succeeded" if succeeded else "failed"

    def mark_filesystem_cleanup(self, install_id, *, succeeded, error=None):
        self.calls.append(("cleanup", install_id, succeeded, error))
        self.row["filesystem_cleanup_state"] = (
            "succeeded" if succeeded else "failed"
        )

    def get(self, _install_id):
        return dict(self.row)


def _row(tmp_path: Path):
    root, _target, _previous, _staging, filesystem, manifest_hash = (
        _filesystem_fixture(tmp_path)
    )
    row = {
        "install_id": "install-1",
        "pack_id": "demo",
        "manifest_hash": manifest_hash,
        "projection_state": "pending",
        "filesystem_cleanup_state": "pending",
        "result_payload": {
            "commit_receipt": {
                "install_id": "install-1",
                "pack_id": "demo",
                "manifest_hash": manifest_hash,
            },
            "install_commit_receipt": {"filesystem": filesystem},
            "pack_metadata": {
                "install_projection_manifest": {"code": "demo", "version": "2.0.0"}
            },
        },
    }
    return root, row


def test_reconciler_syncs_projection_before_retained_tree_cleanup(
    monkeypatch,
    tmp_path: Path,
):
    root, row = _row(tmp_path)
    store = _Store(row)
    order = []
    monkeypatch.setattr(
        "backend.app.services.pack_install_reconciliation_core.reconciler.require_runtime_database_mutation_allowed",
        lambda _operation: None,
    )
    monkeypatch.setattr(
        "backend.app.services.pack_install_reconciliation_core.reconciler._sync_install_time_registries",
        lambda **_kwargs: order.append("projection"),
    )
    monkeypatch.setattr(
        "backend.app.services.pack_install_reconciliation_core.reconciler.finalize_committed_filesystem",
        lambda **_kwargs: order.append("cleanup"),
    )

    result = CommittedInstallReconciler(
        store=store,
        local_core_root=root,
    ).reconcile_next()

    assert result["ok"] is True
    assert order == ["projection", "cleanup"]
    assert store.calls[0][0] == "projection"
    assert store.calls[1][0] == "cleanup"


def test_reconciler_keeps_previous_tree_when_projection_sync_fails(
    monkeypatch,
    tmp_path: Path,
):
    root, row = _row(tmp_path)
    store = _Store(row)
    cleanup_called = []
    monkeypatch.setattr(
        "backend.app.services.pack_install_reconciliation_core.reconciler.require_runtime_database_mutation_allowed",
        lambda _operation: None,
    )
    monkeypatch.setattr(
        "backend.app.services.pack_install_reconciliation_core.reconciler._sync_install_time_registries",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("projection failed")),
    )
    monkeypatch.setattr(
        "backend.app.services.pack_install_reconciliation_core.reconciler.finalize_committed_filesystem",
        lambda **_kwargs: cleanup_called.append(True),
    )

    result = CommittedInstallReconciler(
        store=store,
        local_core_root=root,
    ).reconcile_next()

    assert result["ok"] is False
    assert "projection failed" in result["error"]
    assert cleanup_called == []
    assert store.calls[0][0:3] == ("projection", "install-1", False)


def test_clean_reconciliation_poll_is_cached_for_worker_idle_budget(monkeypatch):
    calls = []

    class _CleanReconciler:
        def reconcile_next(self):
            calls.append("next")
            return None

        def has_incomplete(self):
            calls.append("incomplete")
            return False

    monkeypatch.setattr(
        pack_install_reconciliation,
        "CommittedInstallReconciler",
        _CleanReconciler,
    )
    monkeypatch.setattr(pack_install_reconciliation.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        pack_install_reconciliation,
        "_clean_until_monotonic",
        0.0,
    )

    assert pack_install_reconciliation.poll_install_reconciliation_once() is None
    assert pack_install_reconciliation.poll_install_reconciliation_once() is None
    assert calls == ["next", "incomplete"]


def test_future_reconciliation_retry_blocks_new_install_claim(monkeypatch):
    class _WaitingReconciler:
        def reconcile_next(self):
            return None

        def has_incomplete(self):
            return True

    monkeypatch.setattr(
        pack_install_reconciliation,
        "CommittedInstallReconciler",
        _WaitingReconciler,
    )
    monkeypatch.setattr(pack_install_reconciliation.time, "monotonic", lambda: 200.0)
    monkeypatch.setattr(
        pack_install_reconciliation,
        "_clean_until_monotonic",
        0.0,
    )

    result = pack_install_reconciliation.poll_install_reconciliation_once()

    assert result == {
        "kind": "pack_install_reconciliation",
        "ok": False,
        "state": "waiting_retry_window",
        "retry_after_seconds": 30,
    }
