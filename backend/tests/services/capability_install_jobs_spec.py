import pytest

from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    DatabaseWriteReadiness,
)
from backend.app.services import capability_install_jobs
from backend.app.services.capability_install_jobs import CapabilityInstallJobService


class _FakeStore:
    def __init__(self):
        self.waiting = None

    def claim_next_job(self):
        return {
            "install_id": "job-1",
            "source_kind": "file_upload",
            "source_payload": {
                "mindpack_path": "/tmp/demo.mindpack",
                "allow_overwrite": False,
                "overwrite_review_confirmation": "",
            },
        }

    def mark_waiting_db(self, install_id, *, reason, retry_after_seconds):
        self.waiting = {
            "install_id": install_id,
            "state": "waiting_db",
            "reason": reason,
            "retry_after_seconds": retry_after_seconds,
        }
        return self.waiting


@pytest.mark.asyncio
async def test_install_job_enters_waiting_db_before_filesystem_promotion(monkeypatch):
    readiness = DatabaseWriteReadiness(
        ready=False,
        reason="postgres_recovery_in_progress",
        retry_after_seconds=17,
    )

    def fail_readiness(**_kwargs):
        raise DatabaseWriteNotReadyError(readiness)

    monkeypatch.setattr(
        capability_install_jobs,
        "wait_for_core_write_readiness",
        fail_readiness,
    )
    store = _FakeStore()
    service = CapabilityInstallJobService(store=store)

    result = await service.run_next_job(fastapi_app=object())

    assert result == {
        "install_id": "job-1",
        "state": "waiting_db",
        "reason": "postgres_recovery_in_progress",
        "retry_after_seconds": 17,
    }
    assert store.waiting == result
