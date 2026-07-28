from types import SimpleNamespace

import pytest

from backend.app.routes.core.capability_install_core.install_commit_core.coordinator import (
    InstallCommitCoordinator,
)
from backend.app.routes.core.capability_install_core.install_commit_core.filesystem_saga import (
    PreparedCapabilityTree,
)
from backend.app.routes.core.capability_install_core.install_commit_core.state_machine import (
    InstallCommitState,
)
from backend.app.services import pack_install_reconciliation
from backend.app.services.capability_install_jobs_core import executor
from backend.app.services.runtime_assets_installer_staging import (
    RuntimeAssetsInstallerStagingMixin,
)


def test_discard_restored_candidate_keeps_live_tree_and_removes_retained_roots(
    tmp_path,
):
    capabilities_dir = tmp_path / "app" / "capabilities"
    target_cap_dir = capabilities_dir / "ig"
    target_cap_dir.mkdir(parents=True)
    (target_cap_dir / "manifest.yaml").write_text(
        'version: "1.0.201"\n',
        encoding="utf-8",
    )
    staging_root = tmp_path / "app" / ".capability-install-staging" / "job-1"
    staging_cap_dir = staging_root / "ig"
    staging_cap_dir.mkdir(parents=True)
    (staging_cap_dir / "manifest.yaml").write_text(
        'version: "1.0.202"\n',
        encoding="utf-8",
    )
    previous_root = tmp_path / "app" / ".capability-install-previous" / "job-1"
    previous_cap_dir = previous_root / "ig"
    previous_root.mkdir(parents=True)
    prepared = PreparedCapabilityTree(
        install_id="job-1",
        capability_code="ig",
        staging_root=staging_root,
        staging_cap_dir=staging_cap_dir,
        target_cap_dir=target_cap_dir,
        previous_root=previous_root,
        previous_cap_dir=previous_cap_dir,
    )

    RuntimeAssetsInstallerStagingMixin().discard_restored_candidate(prepared)

    assert not staging_root.exists()
    assert not previous_root.exists()
    assert (target_cap_dir / "manifest.yaml").read_text(encoding="utf-8") == (
        'version: "1.0.201"\n'
    )


def test_coordinator_allows_discard_only_after_previous_tree_is_restored():
    calls = []

    class FakeRuntimeInstaller:
        def discard_restored_candidate(self, prepared):
            calls.append(prepared)

    coordinator = InstallCommitCoordinator(
        install_id="job-1",
        capability_code="ig",
        runtime_installer=FakeRuntimeInstaller(),
    )
    coordinator.prepared = object()
    coordinator.state = InstallCommitState.RESTORED_PREVIOUS

    coordinator.discard_restored_candidate()

    assert calls == [coordinator.prepared]


@pytest.mark.asyncio
async def test_pending_activation_discards_candidate_before_job_requeue(
    monkeypatch,
):
    class FakeCoordinator:
        truth_committed = False

        def __init__(self):
            self.discarded = False

        def discard_restored_candidate(self):
            self.discarded = True

        def receipt(self):
            return {"state": "restored_previous", "discarded": self.discarded}

    coordinator = FakeCoordinator()
    pipeline_result = SimpleNamespace(install_commit_coordinator=coordinator)

    class FakeStore:
        def claim_next_job(self):
            return {
                "install_id": "job-1",
                "source_kind": "file_upload",
                "source_payload": {"archive_sha256": "a" * 64},
            }

        def mark_pending_execution_activation(
            self,
            install_id,
            *,
            result_payload,
            error,
        ):
            assert coordinator.discarded is True
            return {
                "install_id": install_id,
                "state": "pending_execution_activation",
                "result_payload": result_payload,
                "error": error,
            }

    class FakeService:
        def __init__(self):
            self.store = FakeStore()

        async def _notify_execution_activation(self, **kwargs):
            return {
                "state": "pending_execution_activation",
                "error": "activation_timeout",
            }

        def _refresh_restart_payload(self, payload, **kwargs):
            return payload

    async def fake_execute_pipeline_job(*args, **kwargs):
        return pipeline_result

    async def fake_restore_previous_runtime(*args, **kwargs):
        return {"state": "activated", "version": "1.0.201"}

    monkeypatch.setattr(
        pack_install_reconciliation,
        "poll_install_reconciliation_once",
        lambda: None,
    )
    monkeypatch.setattr(
        executor,
        "require_runtime_database_mutation_allowed",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        executor,
        "execute_pipeline_job",
        fake_execute_pipeline_job,
    )
    monkeypatch.setattr(
        executor,
        "pipeline_payload",
        lambda result: {
            "capability_code": "ig",
            "activation_candidate": {"manifest_hash": "candidate-hash"},
        },
    )
    monkeypatch.setattr(
        executor.install_integrity,
        "attach_install_integrity_evidence",
        lambda **kwargs: kwargs["result_payload"],
    )
    monkeypatch.setattr(
        executor,
        "_restore_previous_runtime",
        fake_restore_previous_runtime,
    )

    result = await executor.run_next_job(
        FakeService(),
        fastapi_app=object(),
    )

    assert result["state"] == "pending_execution_activation"
    assert result["result_payload"]["install_commit_receipt"] == {
        "state": "restored_previous",
        "discarded": True,
    }
